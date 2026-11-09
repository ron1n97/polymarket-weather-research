from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from meteostat import Point, hourly, stations


UTC = timezone.utc


@dataclass(frozen=True)
class CityConfig:
    slug: str
    label: str
    icao: str
    airport_lat: float
    airport_lon: float


CITIES: list[CityConfig] = [
    CityConfig("tokyo", "Tokyo", "RJTT", 35.5494, 139.7798),
    CityConfig("seoul", "Seoul", "RKSI", 37.4602, 126.4407),
    CityConfig("singapore", "Singapore", "WSSS", 1.3644, 103.9915),
    CityConfig("shanghai", "Shanghai", "ZSPD", 31.1443, 121.8083),
    CityConfig("beijing", "Beijing", "ZBAA", 40.0799, 116.6031),
    CityConfig("paris", "Paris", "LFPG", 49.0097, 2.5479),
    CityConfig("london", "London", "EGLC", 51.5053, 0.0553),
    CityConfig("dallas", "Dallas", "KDAL", 32.8471, -96.8518),
    CityConfig("nyc", "New York City", "KLGA", 40.7769, -73.8740),
]


def pick_station(city: CityConfig) -> pd.Series:
    nearby = stations.nearby(Point(city.airport_lat, city.airport_lon), limit=10)
    if nearby.empty:
        raise RuntimeError(f"No nearby stations found for {city.label}")
    station = nearby.iloc[0].copy()
    station["id"] = nearby.index[0]
    return station


def compute_cutoff(local_day: date, tz_name: str) -> datetime:
    local_midnight = pd.Timestamp.combine(local_day, time.min).tz_localize(tz_name)
    return (local_midnight.tz_convert("UTC") + pd.Timedelta(hours=12)).tz_convert(tz_name).to_pydatetime()


def fetch_hourly(city: CityConfig, station_id: str, timezone_name: str, years: int) -> pd.DataFrame:
    end_day = date.today() - timedelta(days=1)
    start_day = end_day - timedelta(days=365 * years)
    frame = hourly(
        station_id,
        start=datetime.combine(start_day, time.min),
        end=datetime.combine(end_day + timedelta(days=1), time.min),
        timezone=timezone_name,
    ).fetch()
    if frame is None or frame.empty:
        raise RuntimeError(f"No hourly data returned for {city.label} ({station_id})")

    frame = frame.reset_index()
    frame = frame.rename(columns={"time": "timestamp", "temp": "temp_c"})
    frame = frame[["timestamp", "temp_c"]].dropna()
    frame["local_day"] = frame["timestamp"].dt.date
    frame["local_hour"] = frame["timestamp"].dt.hour
    return frame


def build_city_stats(city: CityConfig, years: int, output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    station = pick_station(city)
    station_id = str(station["id"])
    timezone_name = str(station["timezone"])

    df = fetch_hourly(city, station_id, timezone_name, years)
    cutoff_by_day = {day: compute_cutoff(day, timezone_name) for day in sorted(df["local_day"].unique())}
    df["deadline_local"] = df["local_day"].map(cutoff_by_day)
    df["eligible"] = df["timestamp"] <= df["deadline_local"]

    daily_final = (
        df.groupby("local_day", as_index=False)["temp_c"]
        .max()
        .rename(columns={"temp_c": "final_day_max_c"})
    )
    df = df.merge(daily_final, on="local_day", how="left")
    df["current_max_c"] = df.groupby("local_day")["temp_c"].cummax()
    df["is_final_max_known"] = df["current_max_c"] >= df["final_day_max_c"]

    eligible = df[df["eligible"]].copy()
    hourly_stats = (
        eligible.groupby("local_hour", as_index=False)
        .agg(
            sample_days=("local_day", "nunique"),
            win_rate=("is_final_max_known", "mean"),
            avg_current_max_c=("current_max_c", "mean"),
            avg_final_max_c=("final_day_max_c", "mean"),
        )
        .sort_values("local_hour")
    )

    hourly_stats["city"] = city.label
    hourly_stats["slug"] = city.slug
    hourly_stats["icao"] = city.icao
    hourly_stats["station_id"] = station_id
    hourly_stats["station_name"] = str(station["name"])
    hourly_stats["timezone"] = timezone_name
    hourly_stats["win_rate_pct"] = hourly_stats["win_rate"] * 100.0

    city_dir = output_dir / city.slug
    city_dir.mkdir(parents=True, exist_ok=True)
    eligible.to_csv(city_dir / "eligible_observations.csv", index=False)
    hourly_stats.to_csv(city_dir / "hourly_winrate.csv", index=False)

    metadata = pd.DataFrame(
        [
            {
                "city": city.label,
                "slug": city.slug,
                "icao": city.icao,
                "station_id": station_id,
                "station_name": str(station["name"]),
                "timezone": timezone_name,
                "station_latitude": station["latitude"],
                "station_longitude": station["longitude"],
                "station_distance_m": station["distance"],
                "sample_days": int(eligible["local_day"].nunique()),
                "start_day": eligible["local_day"].min(),
                "end_day": eligible["local_day"].max(),
                "deadline_hour_min": int(hourly_stats["local_hour"].min()),
                "deadline_hour_max": int(hourly_stats["local_hour"].max()),
            }
        ]
    )
    metadata.to_csv(city_dir / "metadata.csv", index=False)
    return hourly_stats, metadata


def plot_results(all_stats: pd.DataFrame, output_path: Path) -> None:
    cities = list(all_stats["city"].drop_duplicates())
    cols = 3
    rows = (len(cities) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(18, 4.5 * rows), sharey=True)
    axes = axes.flatten()

    for axis, city in zip(axes, cities):
        city_stats = all_stats[all_stats["city"] == city].sort_values("local_hour")
        axis.plot(city_stats["local_hour"], city_stats["win_rate_pct"], color="#0b6e4f", linewidth=2.2)
        axis.scatter(city_stats["local_hour"], city_stats["win_rate_pct"], color="#0b6e4f", s=18)
        final_row = city_stats.iloc[-1]
        axis.set_title(f"{city} ({final_row['icao']})")
        axis.set_xlabel("Local Hour")
        axis.set_ylabel("P(current max = final max), %")
        axis.set_xlim(city_stats["local_hour"].min(), city_stats["local_hour"].max())
        axis.set_ylim(0, 105)
        axis.grid(alpha=0.25)
        axis.text(
            0.02,
            0.04,
            (
                f"deadline window ends at {int(final_row['local_hour']):02d}:00 local\n"
                f"n={int(final_row['sample_days'])} days"
            ),
            transform=axis.transAxes,
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.85, "edgecolor": "#cccccc"},
        )

    for axis in axes[len(cities):]:
        axis.axis("off")

    fig.suptitle("Win Rate of 'Current Max Already Equals Final Daily Max' up to 12:00 UTC Deadline", fontsize=16)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main() -> None:
    years = 3
    output_dir = Path("outputs") / "deadline_winrate"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_stats: list[pd.DataFrame] = []
    all_meta: list[pd.DataFrame] = []
    for city in CITIES:
        stats, metadata = build_city_stats(city, years=years, output_dir=output_dir)
        all_stats.append(stats)
        all_meta.append(metadata)

    all_stats_df = pd.concat(all_stats, ignore_index=True)
    all_meta_df = pd.concat(all_meta, ignore_index=True)
    all_stats_df.to_csv(output_dir / "all_cities_hourly_winrate.csv", index=False)
    all_meta_df.to_csv(output_dir / "all_cities_metadata.csv", index=False)

    plot_results(all_stats_df, output_dir / "deadline_winrate_all_cities.png")

    summary = (
        all_stats_df.sort_values(["city", "local_hour"])
        .groupby("city", as_index=False)
        .tail(1)[["city", "icao", "station_id", "timezone", "local_hour", "sample_days", "win_rate_pct"]]
        .rename(columns={"local_hour": "deadline_hour_local"})
        .sort_values("win_rate_pct", ascending=False)
    )
    summary.to_csv(output_dir / "deadline_snapshot.csv", index=False)
    print(summary.to_string(index=False))
    print(f"\nSaved outputs to: {output_dir}")


if __name__ == "__main__":
    main()
