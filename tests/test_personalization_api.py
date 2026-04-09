from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def personalization_client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "personalization_test.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("AUTO_CREATE_DB", "true")
    monkeypatch.setenv("INLINE_JOB_EXECUTION", "true")
    monkeypatch.setenv("APP_BASE_URL", "http://testserver")
    monkeypatch.setenv("PUBLIC_WEB_BASE_URL", "http://testserver")
    monkeypatch.setenv("PERSONALIZATION_BASE_URL", "http://testserver")

    for module_name in [
        "webapp.config",
        "personalization.db",
        "personalization.models",
        "personalization.security",
        "personalization.session",
        "personalization.rotation",
        "personalization.profile",
        "personalization.imports",
        "personalization.scoring",
        "personalization.strava",
        "personalization.jobs",
        "webapp.deps",
        "webapp.routers.catalog",
        "webapp.routers.personalization",
        "webapp.routers.imports",
        "webapp.routers.rotation",
        "webapp.routers.feedback",
        "webapp.routers.strava",
        "webapp.app_factory",
    ]:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)

    from webapp.app_factory import create_personalization_app
    from personalization.db import ensure_database

    app = create_personalization_app()
    ensure_database()
    return TestClient(app)


def test_personalization_smoke_flow(personalization_client: TestClient) -> None:
    bootstrap = personalization_client.post("/api/personalization/session/bootstrap")
    assert bootstrap.status_code == 200

    profile = personalization_client.get("/api/profile")
    assert profile.status_code == 200
    assert profile.json()["profile_version"] == 1
    assert profile.json()["coverage"]["missing_signals"]

    add_shoe = personalization_client.post(
        "/api/rotation/shoes",
        json={"catalog_shoe_id": "ASICS::ASICS Dynablast 4", "start_mileage_km": 100},
    )
    assert add_shoe.status_code == 200

    rotation = personalization_client.get("/api/rotation")
    assert rotation.status_code == 200
    assert len(rotation.json()["shoes"]) == 1
    assert rotation.json()["summary"]["manual_count"] == 1

    recommendations = personalization_client.get("/api/recommendations/personalized?context=easy")
    assert recommendations.status_code == 200
    payload = recommendations.json()
    assert payload["context"] == "easy"
    assert len(payload["results"]) == 10


def test_imported_unmapped_shoe_appears_in_rotation(personalization_client: TestClient) -> None:
    personalization_client.post("/api/personalization/session/bootstrap")

    csv_payload = (
        b"Activity ID,Start Date,Distance km,Moving Time,Shoe,Type\n"
        b"1,2026-04-01 07:00:00,8.4,00:42:00,My Lucky Racers,Run\n"
    )
    response = personalization_client.post(
        "/api/imports",
        data={"source_type": "csv"},
        files={"file": ("runs.csv", csv_payload, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["unmapped_shoe_count"] == 1

    rotation = personalization_client.get("/api/rotation")
    assert rotation.status_code == 200
    payload = rotation.json()
    assert payload["summary"]["imported_count"] == 1
    assert payload["summary"]["unmapped_count"] == 1
    assert payload["shoes"][0]["source_kind"] == "imported"
    assert payload["shoes"][0]["mapping_status"] == "unmapped"
    assert payload["shoes"][0]["display_name"] == "My Lucky Racers"
    assert payload["shoes"][0]["raw_import_name"] == "My Lucky Racers"


def test_manual_shoe_merges_with_imported_activity(personalization_client: TestClient) -> None:
    personalization_client.post("/api/personalization/session/bootstrap")
    add_shoe = personalization_client.post(
        "/api/rotation/shoes",
        json={"catalog_shoe_id": "ASICS::ASICS Dynablast 4", "start_mileage_km": 100},
    )
    assert add_shoe.status_code == 200

    csv_payload = (
        b"Activity ID,Start Date,Distance km,Moving Time,Shoe,Type\n"
        b"1,2026-04-01 07:00:00,8.4,00:42:00,ASICS Dynablast 4,Run\n"
    )
    response = personalization_client.post(
        "/api/imports",
        data={"source_type": "csv"},
        files={"file": ("runs.csv", csv_payload, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["mapped_shoe_count"] == 1

    rotation = personalization_client.get("/api/rotation")
    payload = rotation.json()
    assert len(payload["shoes"]) == 1
    assert payload["summary"]["manual_count"] == 1
    assert payload["summary"]["imported_count"] == 0
    assert payload["shoes"][0]["source_kind"] == "manual_with_import"
    assert payload["shoes"][0]["activity_count"] == 1
    assert payload["shoes"][0]["current_mileage_km"] == 108.4


def test_import_summary_reports_detected_mapped_and_unmapped_shoes(personalization_client: TestClient) -> None:
    personalization_client.post("/api/personalization/session/bootstrap")

    csv_payload = (
        b"Activity ID,Start Date,Distance km,Moving Time,Shoe,Type\n"
        b"1,2026-04-01 07:00:00,8.4,00:42:00,Nike Pegasus 41,Run\n"
        b"2,2026-04-02 07:00:00,5.0,00:28:00,Custom Mystery Shoe,Run\n"
    )
    response = personalization_client.post(
        "/api/imports",
        data={"source_type": "csv"},
        files={"file": ("runs.csv", csv_payload, "text/csv")},
    )

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["imported_activities"] == 2
    assert summary["detected_shoe_count"] == 2
    assert summary["mapped_shoe_count"] == 1
    assert summary["unmapped_shoe_count"] == 1


def test_personalize_page_uses_your_shoes_inventory_language(personalization_client: TestClient) -> None:
    response = personalization_client.get("/")
    assert response.status_code == 200
    assert "Your shoes" in response.text
    assert "what we know about you" in response.text
