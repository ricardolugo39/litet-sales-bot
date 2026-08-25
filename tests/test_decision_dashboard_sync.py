import gzip
import sqlite3

import pytest


REQUIRED_TABLES = (
    "orders", "business_traffic", "asin_economics", "inventory_snapshots",
    "dim_product", "cogs_ledger", "ppc_fact_clean",
)


def create_database(path, marker=None):
    with sqlite3.connect(path) as conn:
        for table in REQUIRED_TABLES:
            conn.execute(f'CREATE TABLE "{table}" (id INTEGER)')
        if marker is not None:
            conn.execute("CREATE TABLE interventions (id INTEGER PRIMARY KEY, marker TEXT)")
            conn.execute("INSERT INTO interventions(marker) VALUES (?)", (marker,))


@pytest.fixture
def sync_client(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical.db"
    create_database(canonical, marker="keep")
    monkeypatch.setenv("LITET_DB_PATH", str(canonical))
    monkeypatch.setenv("HASTEN_DECISION_DB", str(canonical))
    monkeypatch.setenv("ADMIN_UPLOAD_TOKEN", "secret")
    from decision_dashboard_v2.app import app
    app.config.update(TESTING=True)
    return app.test_client(), canonical


def test_database_upload_requires_authorization(sync_client, tmp_path):
    client, _ = sync_client
    candidate = tmp_path / "candidate.db"
    create_database(candidate)
    response = client.put("/admin/database", data=gzip.compress(candidate.read_bytes()))
    assert response.status_code == 401


def test_database_upload_validates_and_preserves_interventions(sync_client, tmp_path):
    client, canonical = sync_client
    candidate = tmp_path / "candidate.db"
    create_database(candidate)
    response = client.put(
        "/admin/database",
        data=gzip.compress(candidate.read_bytes()),
        headers={"Authorization": "Bearer secret", "Content-Type": "application/gzip"},
    )
    assert response.status_code == 200
    with sqlite3.connect(canonical) as conn:
        assert conn.execute("SELECT marker FROM interventions").fetchone()[0] == "keep"


def test_database_download_returns_valid_snapshot(sync_client, tmp_path):
    client, _ = sync_client
    response = client.get(
        "/admin/database", headers={"Authorization": "Bearer secret"}
    )
    assert response.status_code == 200
    downloaded = tmp_path / "downloaded.db"
    downloaded.write_bytes(gzip.decompress(response.data))
    with sqlite3.connect(downloaded) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_health_allows_initial_database_upload(tmp_path, monkeypatch):
    monkeypatch.setenv("LITET_DB_PATH", str(tmp_path / "not-created-yet.db"))
    from decision_dashboard_v2.app import app
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "initializing"


def test_admin_page_exposes_sync_controls(sync_client):
    client, _ = sync_client
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Validate and upload" in response.data
    assert b"Download offline snapshot" in response.data
