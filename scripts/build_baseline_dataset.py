#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from build_max_progress_report import (
    CITIES,
    CityConfig,
    choose_station,
    iter_hourly_rows,
    load_station_history,
    parse_tmp_tenths_c,
    valid_local_day,
)


@dataclass
class Row:
    city: str
    icao: str
    station_id: str
    station_name: str
    timezone: str
    local_day: str
    cutoff_hour_local: str
    cutoff_timestamp_local: str
    cutoff_timestamp_utc: str
    current_max_c: float
    current_max_rounded_c: int
    final_max_c: float
    final_max_rounded_c: int
    hit_final_max_exact: int
    hit_final_max_rounded: int
    observations_seen: int
    total_observations_day: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a model-ready baseline dataset from hourly airport observations. "
            "Each row is a city/day/cutoff-hour snapshot up to the 12:00 UTC market deadline."
        )
    )
    parser.add_argument("--years", type=int, default=3, help="Number of full calendar years to include. Default: 3")
    parser.add_argument(
        "--cache-dir",
        default="data/noaa-cache",
        help="Directory for downloaded NOAA files. Default: data/noaa-cache",
    )
    parser.add_argument(
        "--output",
        default="outputs/baseline_dataset.csv",
        help="CSV output path. Default: outputs/baseline_dataset.csv",
    )
    parser.add_argument(
        "--summary-output",
        default="outputs/baseline_deadline_summary.csv",
        help="Summary CSV output path. Default: outputs/baseline_deadline_summary.csv",
    )
    parser.add_argument(
        "--min-observations-per-day",
        type=int,
        default=18,
        help="Filter out thin days with too few observations. Default: 18",
    )
    return parser.parse_args()


def collect_rows(
    city: CityConfig,
    station_id: str,
    station_name: str,
    hourly_rows: list[dict[str, str]],
    min_observations_per_day: int,
) -> list[Row]:
    tz = ZoneInfo(city.timezone)
    by_day: dict[date, list[tuple[datetime, int]]] = defaultdict(list)

    for raw_row in hourly_rows:
        tmp = parse_tmp_tenths_c(raw_row.get("TMP", ""))
        if tmp is None:
            continue
        utc_dt = datetime.fromisoformat(raw_row["DATE"]).replace(tzinfo=UTC)
        local_dt = utc_dt.astimezone(tz)
        by_day[local_dt.date()].append((local_dt, tmp))

    result: list[Row] = []
    for local_day, observations in sorted(by_day.items()):
        observations.sort(key=lambda item: item[0])
        if not valid_local_day(observations, min_observations_per_day):
            continue

        final_max_tenths = max(temp for _, temp in observations)
        total_observations = len(observations)
        day_start = datetime.combine(local_day, time(0, 0), tzinfo=tz)
        cutoff_local = datetime.combine(local_day, time(12, 0), tzinfo=UTC).astimezone(tz)
        running_max = -math.inf
        cursor = 0

        for hour in range(24):
            threshold = day_start + timedelta(hours=hour)
            if threshold > cutoff_local:
                break
            while cursor < len(observations) and observations[cursor][0] <= threshold:
                running_max = max(running_max, observations[cursor][1])
                cursor += 1
            if running_max == -math.inf:
                continue

            current_max_c = running_max / 10.0
            final_max_c = final_max_tenths / 10.0
            current_max_rounded_c = round(current_max_c)
            final_max_rounded_c = round(final_max_c)

            result.append(
                Row(
                    city=city.name,
                    icao=city.icao,
                    station_id=station_id,
                    station_name=station_name,
                    timezone=city.timezone,
                    local_day=local_day.isoformat(),
                    cutoff_hour_local=f"{hour:02d}:00",
                    cutoff_timestamp_local=threshold.isoformat(),
                    cutoff_timestamp_utc=threshold.astimezone(UTC).isoformat(),
                    current_max_c=current_max_c,
                    current_max_rounded_c=current_max_rounded_c,
                    final_max_c=final_max_c,
                    final_max_rounded_c=final_max_rounded_c,
                    hit_final_max_exact=int(running_max == final_max_tenths),
                    hit_final_max_rounded=int(current_max_rounded_c == final_max_rounded_c),
                    observations_seen=cursor,
                    total_observations_day=total_observations,
                )
            )

    return result


def write_rows(rows: list[Row], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Row.__annotations__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def write_summary(rows: list[Row], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    deadline_rows: dict[str, Row] = {}
    for row in rows:
        deadline_rows[f"{row.city}:{row.local_day}"] = row

    summary: dict[str, list[Row]] = defaultdict(list)
    for row in deadline_rows.values():
        summary[row.city].append(row)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "city",
            "icao",
            "station_id",
            "timezone",
            "sample_days",
            "deadline_hour_local",
            "baseline_exact_win_rate",
            "baseline_rounded_win_rate",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for city, city_rows in sorted(summary.items()):
            sample_days = len(city_rows)
            exact = sum(row.hit_final_max_exact for row in city_rows) / sample_days
            rounded = sum(row.hit_final_max_rounded for row in city_rows) / sample_days
            first = city_rows[0]
            writer.writerow(
                {
                    "city": city,
                    "icao": first.icao,
                    "station_id": first.station_id,
                    "timezone": first.timezone,
                    "sample_days": sample_days,
                    "deadline_hour_local": first.cutoff_hour_local,
                    "baseline_exact_win_rate": f"{exact:.6f}",
                    "baseline_rounded_win_rate": f"{rounded:.6f}",
                }
            )


def main() -> None:
    args = parse_args()
    cache_dir = Path(args.cache_dir)
    output_path = Path(args.output)
    summary_output_path = Path(args.summary_output)

    current_year = datetime.now(tz=UTC).year
    years = range(current_year - args.years, current_year)
    station_history = load_station_history(cache_dir)

    rows: list[Row] = []
    for city in CITIES:
        station = choose_station(station_history[city.icao], start_year=years.start)
        city_rows = list(iter_hourly_rows(cache_dir, station, years))
        rows.extend(
            collect_rows(
                city=city,
                station_id=station.station_id,
                station_name=station.station_name,
                hourly_rows=city_rows,
                min_observations_per_day=args.min_observations_per_day,
            )
        )

    write_rows(rows, output_path)
    write_summary(rows, summary_output_path)
    print(f"Saved dataset to {output_path}")
    print(f"Saved summary to {summary_output_path}")


if __name__ == "__main__":
    main()
