from personalization.imports import parse_csv_bytes, parse_gpx_bytes


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
