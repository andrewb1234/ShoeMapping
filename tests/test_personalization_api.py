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

    add_shoe = personalization_client.post(
        "/api/rotation/shoes",
        json={"catalog_shoe_id": "ASICS::ASICS Dynablast 4", "start_mileage_km": 100},
    )
    assert add_shoe.status_code == 200

    rotation = personalization_client.get("/api/rotation")
    assert rotation.status_code == 200
    assert len(rotation.json()["shoes"]) == 1

    recommendations = personalization_client.get("/api/recommendations/personalized?context=easy")
    assert recommendations.status_code == 200
    payload = recommendations.json()
    assert payload["context"] == "easy"
    assert len(payload["results"]) == 10
