from personalization.imports import parse_csv_bytes, parse_gpx_bytes, summarize_detected_shoes
from webapp.services import ShoeCatalogService


def test_parse_csv_bytes_maps_common_columns() -> None:
    csv_payload = b"""Activity ID,Start Date,Distance km,Moving Time,Elevation Gain,Average Heart Rate,Cadence,Shoe,Type\n1,2026-04-01 07:00:00,8.4,00:42:00,52,148,172,ASICS Dynablast 4,Run\n"""

    activities, summary, warnings = parse_csv_bytes("runs.csv", csv_payload)

    assert len(activities) == 1
    assert summary["parsed_rows"] == 1
    assert activities[0]["distance_m"] == 8400.0
    assert activities[0]["moving_time_s"] == 2520.0
    assert activities[0]["gear_ref"] == "ASICS Dynablast 4"
    assert warnings == []


def test_parse_gpx_bytes_extracts_distance_and_missing_signal_warnings() -> None:
    gpx_payload = b"""<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="test">\n  <trk><name>Morning Run</name><trkseg>\n    <trkpt lat="35.0" lon="139.0"><ele>10</ele><time>2026-04-01T07:00:00Z</time></trkpt>\n    <trkpt lat="35.0005" lon="139.0005"><ele>32</ele><time>2026-04-01T07:05:00Z</time></trkpt>\n  </trkseg></trk>\n</gpx>\n"""

    activities, summary, warnings = parse_gpx_bytes("trail-run.gpx", gpx_payload)

    assert len(activities) == 1
    assert summary["source_type"] == "gpx"
    assert activities[0]["distance_m"] > 0
    assert activities[0]["terrain_guess"] in {"trail", "road"}
    assert "heart rate" in warnings[0].lower()


def test_summarize_detected_shoes_uses_conservative_catalog_matching() -> None:
    activities = [
        {"gear_ref": "Nike Pegasus 41"},
        {"gear_ref": "Peg 41"},
        {"gear_ref": "Nike Pegasus 41"},
    ]

    summary = summarize_detected_shoes(activities, catalog_service=ShoeCatalogService())

    assert summary["detected_shoe_count"] == 2
    assert summary["mapped_shoe_count"] == 1
    assert summary["unmapped_shoe_count"] == 1

def test_parse_csv_bytes_maps_strava_activity_gear_column() -> None:
    csv_payload = b"""Activity ID,Activity Date,Activity Name,Activity Type,Elapsed Time,Distance,Max Heart Rate,Relative Effort,Commute,Activity Private Note,Activity Gear,Filename\n14338073691,"Apr 26, 2025, 12:02:42 AM",Hike in Michinoku,Run,"",17204,21.72,,,false,"",Brooks Cascadia17 Trail,activities/15299399917.gpx.gz\n"""

    activities, summary, warnings = parse_csv_bytes("activities.csv", csv_payload)

    assert len(activities) == 1
    assert summary["parsed_rows"] == 1
    assert activities[0]["gear_ref"] == "Brooks Cascadia17 Trail"
    assert warnings == []
