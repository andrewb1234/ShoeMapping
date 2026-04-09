from __future__ import annotations

import csv
import json
import math
import xml.etree.ElementTree as ET
from datetime import timezone
from io import StringIO
from typing import Any, Dict, Iterable, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from personalization.models import ActivityFeature, ActivityLabel, ActivityRaw, ActivitySource, LabelSource, RunContext, SourceType, User
from personalization.utils import checksum_for_payload, normalize_text, parse_datetime, utcnow


CSV_ALIASES = {
    "external_id": ["activity id", "id", "run id"],
    "started_at": ["start date", "start time", "started at", "date", "datetime"],
    "distance": ["distance", "distance km", "distance mi", "km", "miles"],
    "moving_time": ["moving time", "duration", "elapsed time", "time"],
    "elevation_gain": ["elevation gain", "elev gain", "climb", "total ascent"],
    "avg_hr": ["avg hr", "average heart rate", "heart rate", "avg heartrate"],
    "avg_cadence": ["avg cadence", "cadence", "average cadence"],
    "gear_ref": ["gear", "shoe", "shoes", "equipment"],
    "sport_type": ["type", "sport type", "activity type"],
    "terrain_guess": ["terrain", "surface"],
    "surface_guess": ["surface", "terrain"],
}


def _find_header_mapping(headers: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    warnings: list[str] = []
    lowered = {normalize_text(header): header for header in headers}
    mapping: dict[str, str] = {}
    for canonical, aliases in CSV_ALIASES.items():
        for alias in aliases:
            for normalized, original in lowered.items():
                if alias in normalized:
                    mapping[canonical] = original
                    break
            if canonical in mapping:
                break
        if canonical not in mapping and canonical in {"started_at", "distance", "moving_time"}:
            warnings.append(f"CSV is missing a clear column for {canonical.replace('_', ' ')}.")
    return mapping, warnings


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    filtered = "".join(ch for ch in text if ch.isdigit() or ch in ".-")
    if not filtered:
        return None
    try:
        return float(filtered)
    except ValueError:
        return None


def _distance_to_meters(value: Any, header: str | None = None) -> float | None:
    if value is None:
        return None
    text = str(value)
    header_text = normalize_text(header)
    numeric = _parse_number(text)
    if numeric is None:
        return None
    if "mile" in text.lower() or " mi" in text.lower() or "mile" in header_text:
        return numeric * 1609.34
    if "km" in text.lower() or " km" in text.lower() or "distance km" in header_text:
        return numeric * 1000.0
    if header_text in {"m", "meters"}:
        return numeric
    if numeric < 100:
        return numeric * 1000.0
    return numeric


def _duration_to_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        parts = [float(part) for part in text.split(":")]
        if len(parts) == 3:
            return (parts[0] * 3600) + (parts[1] * 60) + parts[2]
        if len(parts) == 2:
            return (parts[0] * 60) + parts[1]
    number = _parse_number(text)
    if number is None:
        return None
    if "min" in text.lower():
        return number * 60.0
    if "hour" in text.lower() or "hr" in text.lower():
        return number * 3600.0
    return number


def _is_run(sport_type: str | None) -> bool:
    if not sport_type:
        return True
    lowered = normalize_text(sport_type)
    return "run" in lowered


def parse_csv_bytes(
    filename: str,
    payload: bytes,
    column_mapping: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    text = payload.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(StringIO(text))
    headers = reader.fieldnames or []
    inferred_mapping, warnings = _find_header_mapping(headers)
    mapping = column_mapping or inferred_mapping
    normalized: list[dict[str, Any]] = []
    skipped = 0
    for index, row in enumerate(reader, start=1):
        sport_type = row.get(mapping.get("sport_type", ""), "Run")
        if not _is_run(sport_type):
            skipped += 1
            continue
        started_at = parse_datetime(row.get(mapping.get("started_at", "")))
        distance_m = _distance_to_meters(
            row.get(mapping.get("distance", "")),
            mapping.get("distance"),
        )
        moving_time_s = _duration_to_seconds(row.get(mapping.get("moving_time", "")))
        if started_at is None or distance_m is None or moving_time_s is None:
            skipped += 1
            continue
        normalized.append(
            {
                "external_id": row.get(mapping.get("external_id", "")) or f"{filename}:{index}",
                "started_at": started_at,
                "timezone_name": (started_at.tzinfo.tzname(started_at) if started_at.tzinfo else "UTC"),
                "sport_type": sport_type or "Run",
                "distance_m": distance_m,
                "moving_time_s": moving_time_s,
                "elapsed_time_s": _duration_to_seconds(row.get(mapping.get("elapsed_time", ""))) or moving_time_s,
                "elevation_gain_m": _parse_number(row.get(mapping.get("elevation_gain", ""))) or 0.0,
                "avg_hr": _parse_number(row.get(mapping.get("avg_hr", ""))),
                "avg_cadence": _parse_number(row.get(mapping.get("avg_cadence", ""))),
                "gear_ref": row.get(mapping.get("gear_ref", "")) or None,
                "terrain_guess": row.get(mapping.get("terrain_guess", "")) or None,
                "surface_guess": row.get(mapping.get("surface_guess", "")) or None,
                "payload_json": row,
            }
        )
    summary = {
        "source_type": "csv",
        "filename": filename,
        "parsed_rows": len(normalized),
        "skipped_rows": skipped,
        "column_mapping": mapping,
    }
    return normalized, summary, warnings


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def parse_gpx_bytes(filename: str, payload: bytes) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    root = ET.fromstring(payload)
    points: list[dict[str, Any]] = []
    for trkpt in root.findall(".//{*}trkpt"):
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])
        ele = trkpt.findtext("{*}ele")
        time_value = trkpt.findtext("{*}time")
        hr = trkpt.findtext(".//{*}hr")
        cad = trkpt.findtext(".//{*}cad")
        points.append(
            {
                "lat": lat,
                "lon": lon,
                "ele": float(ele) if ele is not None else None,
                "time": parse_datetime(time_value),
                "hr": _parse_number(hr),
                "cad": _parse_number(cad),
            }
        )
    if len(points) < 2:
        return [], {"source_type": "gpx", "filename": filename, "parsed_rows": 0}, ["GPX file did not contain enough track points."]

    distance_m = 0.0
    elevation_gain_m = 0.0
    positive_hr = []
    positive_cad = []
    for previous, current in zip(points, points[1:]):
        distance_m += _haversine_meters(previous["lat"], previous["lon"], current["lat"], current["lon"])
        if previous["ele"] is not None and current["ele"] is not None and current["ele"] > previous["ele"]:
            elevation_gain_m += current["ele"] - previous["ele"]
        if current["hr"] is not None:
            positive_hr.append(current["hr"])
        if current["cad"] is not None:
            positive_cad.append(current["cad"])

    started_at = next((point["time"] for point in points if point["time"] is not None), utcnow())
    ended_at = next((point["time"] for point in reversed(points) if point["time"] is not None), started_at)
    elapsed_time_s = max((ended_at - started_at).total_seconds(), 0.0)
    moving_time_s = elapsed_time_s
    elevation_per_km = elevation_gain_m / max(distance_m / 1000.0, 1.0)
    terrain_guess = "trail" if elevation_per_km >= 45 or "trail" in normalize_text(filename) else "road"
    surface_guess = "trail" if terrain_guess == "trail" else "road"
    normalized = [
        {
            "external_id": filename,
            "started_at": started_at.astimezone(timezone.utc),
            "timezone_name": (started_at.tzinfo.tzname(started_at) if started_at.tzinfo else "UTC"),
            "sport_type": "Run",
            "distance_m": distance_m,
            "moving_time_s": moving_time_s,
            "elapsed_time_s": elapsed_time_s,
            "elevation_gain_m": elevation_gain_m,
            "avg_hr": (sum(positive_hr) / len(positive_hr)) if positive_hr else None,
            "avg_cadence": (sum(positive_cad) / len(positive_cad)) if positive_cad else None,
            "gear_ref": None,
            "terrain_guess": terrain_guess,
            "surface_guess": surface_guess,
            "payload_json": {"filename": filename, "points": len(points)},
        }
    ]
    warnings = []
    if not positive_hr:
        warnings.append("GPX file did not contain heart rate data.")
    if not positive_cad:
        warnings.append("GPX file did not contain cadence data.")
    summary = {
        "source_type": "gpx",
        "filename": filename,
        "parsed_rows": 1,
        "distance_km": round(distance_m / 1000.0, 2),
    }
    return normalized, summary, warnings


def store_normalized_activities(
    session: Session,
    user: User,
    source_type: SourceType,
    normalized_activities: List[dict[str, Any]],
    scope_json: dict[str, Any],
) -> dict[str, Any]:
    source = ActivitySource(
        user_id=user.id,
        source_type=source_type.value,
        status="complete",
        scope_json=scope_json,
        last_sync_at=utcnow(),
    )
    session.add(source)
    session.flush()

    imported = 0
    duplicates = 0
    for activity in normalized_activities:
        checksum = checksum_for_payload(
            [
                activity.get("external_id"),
                activity.get("started_at"),
                activity.get("distance_m"),
                activity.get("moving_time_s"),
                activity.get("gear_ref"),
            ]
        )
        existing = session.scalar(
            select(ActivityRaw).where(ActivityRaw.user_id == user.id, ActivityRaw.checksum == checksum)
        )
        if existing:
            duplicates += 1
            continue
        moving_time_s = activity.get("moving_time_s")
        distance_m = activity.get("distance_m")
        avg_pace_mps = (distance_m / moving_time_s) if distance_m and moving_time_s else None
        raw = ActivityRaw(
            user_id=user.id,
            source_id=source.id,
            external_id=activity.get("external_id"),
            checksum=checksum,
            payload_json=activity.get("payload_json") or {},
            started_at=activity["started_at"],
            timezone_name=activity.get("timezone_name"),
            sport_type=activity.get("sport_type") or "Run",
        )
        session.add(raw)
        session.flush()
        session.add(
            ActivityFeature(
                activity_id=raw.id,
                distance_m=distance_m,
                moving_time_s=moving_time_s,
                elapsed_time_s=activity.get("elapsed_time_s") or moving_time_s,
                elevation_gain_m=activity.get("elevation_gain_m"),
                avg_pace_mps=avg_pace_mps,
                avg_hr=activity.get("avg_hr"),
                avg_cadence=activity.get("avg_cadence"),
                surface_guess=activity.get("surface_guess"),
                terrain_guess=activity.get("terrain_guess"),
                has_hr=activity.get("avg_hr") is not None,
                has_cadence=activity.get("avg_cadence") is not None,
                gear_ref=activity.get("gear_ref"),
            )
        )
        session.add(
            ActivityLabel(
                activity_id=raw.id,
                run_context=RunContext.unknown.value,
                context_confidence=0.1,
                label_source=LabelSource.auto.value,
            )
        )
        imported += 1
    session.commit()
    return {"imported_activities": imported, "duplicates": duplicates, "source_id": source.id}
