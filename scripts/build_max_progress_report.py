#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen
from zoneinfo import ZoneInfo


STATION_HISTORY_URL = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
GLOBAL_HOURLY_URL = "https://www.ncei.noaa.gov/data/global-hourly/access/{year}/{station_id}.csv"


@dataclass(frozen=True)
class CityConfig:
    name: str
    icao: str
    timezone: str


CITIES: tuple[CityConfig, ...] = (
    CityConfig("Tokyo", "RJTT", "Asia/Tokyo"),
    CityConfig("Seoul", "RKSI", "Asia/Seoul"),
    CityConfig("Singapore", "WSSS", "Asia/Singapore"),
    CityConfig("Shanghai", "ZSPD", "Asia/Shanghai"),
    CityConfig("Beijing", "ZBAA", "Asia/Shanghai"),
    CityConfig("Shenzhen", "ZGSZ", "Asia/Shanghai"),
    CityConfig("Chongqing", "ZUCK", "Asia/Shanghai"),
    CityConfig("Wuhan", "ZHHH", "Asia/Shanghai"),
    CityConfig("Chengdu", "ZUUU", "Asia/Shanghai"),
    CityConfig("Hong Kong", "VHHH", "Asia/Hong_Kong"),
    CityConfig("Taipei", "RCTP", "Asia/Taipei"),
    CityConfig("Kuala Lumpur", "WMKK", "Asia/Kuala_Lumpur"),
    CityConfig("Paris", "LFPG", "Europe/Paris"),
    CityConfig("London", "EGLC", "Europe/London"),
    CityConfig("Dallas", "KDAL", "America/Chicago"),
    CityConfig("New York City", "KLGA", "America/New_York"),
)


@dataclass
class StationRecord:
    usaf: str
    wban: str
    station_name: str
    icao: str
    begin: date
    end: date

    @property
    def station_id(self) -> str:
        return f"{self.usaf}{self.wban}"


@dataclass
class CityPoint:
    hour: int
    rate: float
    wins: int
    total: int


@dataclass
class CityReport:
    city: CityConfig
    station: StationRecord
    sample_days: int
    cutoff_label: str
    points: list[CityPoint]

    @property
    def cutoff_win_rate(self) -> float:
        if not self.points:
            return 0.0
        return self.points[-1].rate

    @property
    def first_hour_above_99(self) -> int | None:
        for point in self.points:
            if point.rate >= 0.99:
                return point.hour
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a report showing when the current observed max temperature "
            "already equals the final daily max."
        )
    )
    parser.add_argument(
        "--years",
        type=int,
        default=3,
        help="Number of full calendar years to include. Default: 3",
    )
    parser.add_argument(
        "--output",
        default="outputs/max_seen_winrate.html",
        help="HTML output path. Default: outputs/max_seen_winrate.html",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/noaa-cache",
        help="Directory for downloaded NOAA files. Default: data/noaa-cache",
    )
    parser.add_argument(
        "--min-observations-per-day",
        type=int,
        default=18,
        help="Filter out thin days with too few observations. Default: 18",
    )
    return parser.parse_args()


def ensure_cached(url: str, cache_path: Path) -> Path:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if not cache_path.exists():
        with urlopen(url, timeout=60) as response:
            cache_path.write_bytes(response.read())
    return cache_path


def load_station_history(cache_dir: Path) -> dict[str, list[StationRecord]]:
    station_history_path = ensure_cached(STATION_HISTORY_URL, cache_dir / "isd-history.csv")
    records_by_icao: dict[str, list[StationRecord]] = defaultdict(list)
    with station_history_path.open(encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            icao = row["ICAO"].strip()
            if not icao:
                continue
            records_by_icao[icao].append(
                StationRecord(
                    usaf=row["USAF"].strip(),
                    wban=row["WBAN"].strip(),
                    station_name=row["STATION NAME"].strip(),
                    icao=icao,
                    begin=datetime.strptime(row["BEGIN"], "%Y%m%d").date(),
                    end=datetime.strptime(row["END"], "%Y%m%d").date(),
                )
            )
    return records_by_icao


def choose_station(records: Iterable[StationRecord], start_year: int) -> StationRecord:
    candidates = [
        record
        for record in records
        if record.end >= date(start_year, 1, 1)
    ]
    if not candidates:
        raise ValueError("No active station record found for requested range.")
    candidates.sort(key=lambda record: (record.end, record.begin, record.station_id), reverse=True)
    return candidates[0]


def iter_hourly_rows(cache_dir: Path, station: StationRecord, years: range) -> Iterable[dict[str, str]]:
    for year in years:
        cache_path = cache_dir / "global-hourly" / str(year) / f"{station.station_id}.csv"
        local_path = ensure_cached(
            GLOBAL_HOURLY_URL.format(year=year, station_id=station.station_id),
            cache_path,
        )
        with local_path.open(encoding="utf-8", errors="ignore", newline="") as handle:
            yield from csv.DictReader(handle)


def parse_tmp_tenths_c(raw_value: str) -> int | None:
    value = raw_value.split(",", 1)[0]
    if value in {"+9999", "-9999", "9999", ""}:
        return None
    return int(value)


def valid_local_day(
    observations: list[tuple[datetime, int]],
    min_observations_per_day: int,
) -> bool:
    if len(observations) < min_observations_per_day:
        return False
    last_seen = observations[-1][0]
    first_seen = observations[0][0]
    if first_seen.hour > 2:
        return False
    if last_seen.hour < 21:
        return False
    return True


def build_city_report(
    city: CityConfig,
    station: StationRecord,
    hourly_rows: Iterable[dict[str, str]],
    min_observations_per_day: int,
) -> CityReport:
    tz = ZoneInfo(city.timezone)
    by_day: dict[date, list[tuple[datetime, int]]] = defaultdict(list)

    for row in hourly_rows:
        tmp = parse_tmp_tenths_c(row.get("TMP", ""))
        if tmp is None:
            continue
        utc_dt = datetime.fromisoformat(row["DATE"]).replace(tzinfo=UTC)
        local_dt = utc_dt.astimezone(tz)
        by_day[local_dt.date()].append((local_dt, tmp))

    wins: dict[int, int] = defaultdict(int)
    totals: dict[int, int] = defaultdict(int)
    sample_days = 0

    for local_day, observations in by_day.items():
        observations.sort(key=lambda item: item[0])
        if not valid_local_day(observations, min_observations_per_day):
            continue

        final_max = max(temp for _, temp in observations)
        sample_days += 1
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
            totals[hour] += 1
            if running_max == final_max:
                wins[hour] += 1

    cutoff_hours = sorted(totals)
    points = [
        CityPoint(
            hour=hour,
            rate=(wins[hour] / totals[hour]) if totals[hour] else 0.0,
            wins=wins[hour],
            total=totals[hour],
        )
        for hour in cutoff_hours
    ]
    cutoff_label = f"{cutoff_hours[-1]:02d}:00 local" if cutoff_hours else "no data"
    return CityReport(
        city=city,
        station=station,
        sample_days=sample_days,
        cutoff_label=cutoff_label,
        points=points,
    )


def svg_line_chart(points: list[CityPoint], width: int = 760, height: int = 260) -> str:
    if not points:
        return '<svg viewBox="0 0 760 260" class="chart-empty"><text x="24" y="42">No data</text></svg>'

    left = 52
    top = 18
    right = 20
    bottom = 36
    chart_width = width - left - right
    chart_height = height - top - bottom
    max_hour = max(point.hour for point in points)
    max_hour = max(max_hour, 1)

    def x_for(hour: int) -> float:
        return left + (hour / max_hour) * chart_width

    def y_for(rate: float) -> float:
        return top + (1 - rate) * chart_height

    y_ticks = [0.0, 0.25, 0.5, 0.75, 1.0]
    path = " ".join(
        (
            f"{'M' if index == 0 else 'L'} {x_for(point.hour):.2f} {y_for(point.rate):.2f}"
            for index, point in enumerate(points)
        )
    )

    circles = "\n".join(
        f'<circle cx="{x_for(point.hour):.2f}" cy="{y_for(point.rate):.2f}" r="4" />'
        for point in points
    )
    x_labels = "\n".join(
        f'<text x="{x_for(point.hour):.2f}" y="{height - 10}" text-anchor="middle">{point.hour:02d}</text>'
        for point in points
    )
    y_guides = "\n".join(
        (
            f'<line x1="{left}" y1="{y_for(tick):.2f}" x2="{width - right}" y2="{y_for(tick):.2f}" />'
            f'<text x="{left - 10}" y="{y_for(tick) + 4:.2f}" text-anchor="end">{int(tick * 100)}%</text>'
        )
        for tick in y_ticks
    )
    first_above_99 = next((point for point in points if point.rate >= 0.99), None)
    threshold_marker = ""
    if first_above_99 is not None:
        marker_x = x_for(first_above_99.hour)
        marker_y = y_for(first_above_99.rate)
        threshold_marker = f"""
  <line x1="{marker_x:.2f}" y1="{top}" x2="{marker_x:.2f}" y2="{height - bottom}" class="threshold-line" />
  <circle cx="{marker_x:.2f}" cy="{marker_y:.2f}" r="5.5" class="threshold-point" />
  <text x="{marker_x + 8:.2f}" y="{top + 16:.2f}" class="threshold-label">99% at {first_above_99.hour:02d}:00</text>
""".rstrip()

    return f"""
<svg viewBox="0 0 {width} {height}" class="chart">
  <g class="grid">{y_guides}</g>
  <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" class="axis" />
  <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" class="axis" />
  {threshold_marker}
  <path d="{path}" class="series" />
  <g class="points">{circles}</g>
  <g class="x-labels">{x_labels}</g>
</svg>
""".strip()


def render_html(reports: list[CityReport], years: range) -> str:
    generated_at = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    rows = "\n".join(
        (
            f"<tr><td>{html.escape(report.city.name)}</td>"
            f"<td>{html.escape(report.station.icao)}</td>"
            f"<td>{html.escape(report.station.station_name)}</td>"
            f"<td>{report.sample_days}</td>"
            f"<td>{html.escape(report.cutoff_label)}</td>"
            f"<td>{'not reached' if report.first_hour_above_99 is None else f'{report.first_hour_above_99:02d}:00'}</td>"
            f"<td>{report.cutoff_win_rate * 100:.1f}%</td></tr>"
        )
        for report in sorted(reports, key=lambda item: item.cutoff_win_rate, reverse=True)
    )

    cards = "\n".join(
        f"""
<section class="card">
  <div class="card-head">
    <div>
      <h2>{html.escape(report.city.name)}</h2>
      <p>{html.escape(report.city.icao)} · {html.escape(report.station.station_name)}</p>
    </div>
    <div class="metrics">
      <span>{report.sample_days} valid days</span>
      <span>cutoff: {html.escape(report.cutoff_label)}</span>
      <span>99% mark: {"not reached" if report.first_hour_above_99 is None else f"{report.first_hour_above_99:02d}:00 local"}</span>
      <span>win rate at cutoff: {report.cutoff_win_rate * 100:.1f}%</span>
    </div>
  </div>
  {svg_line_chart(report.points)}
</section>
""".strip()
        for report in reports
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Observed Max Progress Report</title>
  <style>
    :root {{
      --bg: #f4f0e8;
      --paper: #fffaf1;
      --ink: #1f2430;
      --muted: #5f6472;
      --accent: #0c6d62;
      --accent-soft: rgba(12, 109, 98, 0.14);
      --grid: rgba(31, 36, 48, 0.16);
      --border: rgba(31, 36, 48, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(12, 109, 98, 0.08), transparent 35%),
        linear-gradient(180deg, #e8efe7 0%, var(--bg) 28%, #efe3d2 100%);
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 36px 0 64px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3.8rem);
      line-height: 0.96;
      letter-spacing: -0.04em;
    }}
    .lede {{
      max-width: 860px;
      margin: 0;
      color: var(--muted);
      font-size: 1.05rem;
    }}
    .summary {{
      margin-top: 28px;
      background: rgba(255, 250, 241, 0.82);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px 22px;
      box-shadow: 0 14px 36px rgba(31, 36, 48, 0.08);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--border);
    }}
    th {{
      font-size: 0.8rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 18px;
      margin-top: 24px;
    }}
    .card {{
      background: rgba(255, 250, 241, 0.84);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 18px;
      box-shadow: 0 12px 28px rgba(31, 36, 48, 0.08);
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      margin-bottom: 14px;
    }}
    .card-head h2 {{
      margin: 0;
      font-size: 1.5rem;
      letter-spacing: -0.03em;
    }}
    .card-head p {{
      margin: 4px 0 0;
      color: var(--muted);
    }}
    .metrics {{
      display: flex;
      flex-direction: column;
      gap: 4px;
      align-items: flex-end;
      font-size: 0.92rem;
      color: var(--muted);
    }}
    .chart {{
      width: 100%;
      height: auto;
      display: block;
      background: linear-gradient(180deg, rgba(12, 109, 98, 0.03), transparent);
      border-radius: 14px;
      overflow: visible;
    }}
    .grid line {{
      stroke: var(--grid);
      stroke-width: 1;
    }}
    .axis {{
      stroke: rgba(31, 36, 48, 0.5);
      stroke-width: 1.2;
    }}
    .series {{
      fill: none;
      stroke: var(--accent);
      stroke-width: 3.2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }}
    .threshold-line {{
      stroke: #b54d14;
      stroke-width: 2;
      stroke-dasharray: 6 5;
    }}
    .threshold-point {{
      fill: #b54d14;
      stroke: var(--paper);
      stroke-width: 2;
    }}
    .threshold-label {{
      fill: #b54d14;
      font-weight: 700;
    }}
    .points circle {{
      fill: var(--paper);
      stroke: var(--accent);
      stroke-width: 2;
    }}
    svg text {{
      font-family: ui-monospace, "SFMono-Regular", "SF Mono", monospace;
      fill: var(--muted);
      font-size: 11px;
    }}
    .footnote {{
      margin-top: 20px;
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.55;
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100% - 20px, 1180px); padding-top: 24px; }}
      .card-head {{ flex-direction: column; }}
      .metrics {{ align-items: flex-start; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>When Is The Max Already Locked?</h1>
      <p class="lede">
        Running-max win rate by local hour for {len(reports)} Polymarket-style airport stations.
        Each point shows the share of valid historical days where the highest observed temperature
        seen by that hour already matched the final daily maximum.
      </p>
    </header>

    <section class="summary">
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>ICAO</th>
            <th>Station</th>
            <th>Valid days</th>
            <th>12:00 UTC cutoff</th>
            <th>First hour >= 99%</th>
            <th>Win rate at cutoff</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </section>

    <section class="grid">
      {cards}
    </section>

    <p class="footnote">
      Period: {years.start} to {years.stop - 1}. Generated: {generated_at}. Data source: NOAA Global Hourly station CSVs
      selected from NOAA ISD station history by ICAO. A day is counted as valid only if it has enough intraday observations
      and reaches late local evening, to reduce bias from incomplete daily files.
    </p>
  </main>
</body>
</html>
"""


def write_csv(reports: list[CityReport], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "city",
                "icao",
                "station_id",
                "station_name",
                "sample_days",
                "hour_local",
                "win_rate",
                "wins",
                "total",
            ]
        )
        for report in reports:
            for point in report.points:
                writer.writerow(
                    [
                        report.city.name,
                        report.city.icao,
                        report.station.station_id,
                        report.station.station_name,
                        report.sample_days,
                        f"{point.hour:02d}:00",
                        f"{point.rate:.6f}",
                        point.wins,
                        point.total,
                    ]
                )


def main() -> None:
    args = parse_args()
    today_utc = datetime.now(tz=UTC).date()
    end_year = today_utc.year - 1
    start_year = end_year - args.years + 1
    years = range(start_year, end_year + 1)

    cache_dir = Path(args.cache_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    station_history = load_station_history(cache_dir)
    reports: list[CityReport] = []

    for city in CITIES:
        if city.icao not in station_history:
            raise KeyError(f"No NOAA station history found for ICAO {city.icao}")
        station = choose_station(station_history[city.icao], start_year)
        reports.append(
            build_city_report(
                city=city,
                station=station,
                hourly_rows=iter_hourly_rows(cache_dir, station, years),
                min_observations_per_day=args.min_observations_per_day,
            )
        )

    html_output = render_html(reports, years)
    output_path.write_text(html_output, encoding="utf-8")
    csv_output_path = output_path.with_suffix(".csv")
    write_csv(reports, csv_output_path)
    print(f"Saved report to {output_path}")
    print(f"Saved hourly stats to {csv_output_path}")
    for report in sorted(reports, key=lambda item: item.cutoff_win_rate, reverse=True):
        print(
            f"{report.city.name:14s} cutoff={report.cutoff_label:>12s} "
            f"win_rate={report.cutoff_win_rate * 100:5.1f}% valid_days={report.sample_days}"
        )


if __name__ == "__main__":
    main()
