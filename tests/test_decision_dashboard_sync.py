import gzip
import json
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


def helium_payload(captured_at="2026-08-29"):
    def brand(parent, keyword):
        return {
            "parent_asin": parent,
            "own": {"sales": 100, "revenue": 2000, "price": 14.99,
                    "reviews": 100, "rating": 4.5, "top10_keywords": 10,
                    "sales_change": 5},
            "competitors": [{"name": "Peer", "parent": "B000000001",
                             "segment": "direct", "price": 12.99, "sales": 200,
                             "reviews": 300, "top10_keywords": 20,
                             "sales_change": 3}],
            "keywords": [{"phrase": keyword, "search_volume": 1000,
                          "rank": 12, "peer_rank": 8}],
        }
    return {"captured_at": captured_at, "marketplace": "US", "brands": {
        "Litet": brand("B0DSCFD253", "cycling socks"),
        "Has10": brand("B0CHMVPCC7", "football spats"),
    }}


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


def test_helium_snapshot_requires_authorization(sync_client):
    client, _ = sync_client
    response = client.put("/admin/helium-snapshot", json=helium_payload())
    assert response.status_code == 401


def test_helium_snapshot_requires_both_brands_and_persists_history(sync_client):
    client, canonical = sync_client
    headers = {"Authorization": "Bearer secret"}
    incomplete = helium_payload()
    del incomplete["brands"]["Has10"]
    response = client.put("/admin/helium-snapshot", json=incomplete, headers=headers)
    assert response.status_code == 400

    for captured_at in ("2026-08-28", "2026-08-29"):
        response = client.put(
            "/admin/helium-snapshot",
            json=helium_payload(captured_at),
            headers=headers,
        )
        assert response.status_code == 200
    with sqlite3.connect(canonical) as conn:
        rows = conn.execute(
            "SELECT captured_at, payload_json FROM helium_snapshots ORDER BY captured_at"
        ).fetchall()
    assert [row[0] for row in rows] == ["2026-08-28", "2026-08-29"]
    assert set(json.loads(rows[-1][1])["brands"]) == {"Litet", "Has10"}


def test_database_upload_preserves_helium_history(sync_client, tmp_path):
    client, canonical = sync_client
    headers = {"Authorization": "Bearer secret"}
    assert client.put(
        "/admin/helium-snapshot", json=helium_payload(), headers=headers
    ).status_code == 200
    candidate = tmp_path / "candidate-without-helium.db"
    create_database(candidate)
    response = client.put(
        "/admin/database",
        data=gzip.compress(candidate.read_bytes()),
        headers={**headers, "Content-Type": "application/gzip"},
    )
    assert response.status_code == 200
    with sqlite3.connect(canonical) as conn:
        assert conn.execute("SELECT COUNT(*) FROM helium_snapshots").fetchone()[0] == 1


def test_market_context_reads_latest_database_snapshot(sync_client):
    client, _ = sync_client
    payload = helium_payload()
    payload["brands"]["Has10"]["own"]["sales"] = 777
    response = client.put(
        "/admin/helium-snapshot",
        json=payload,
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200
    from decision_dashboard_v2.analytics import market_context
    context = market_context("Has10")
    assert context["own"]["sales"] == 777
    assert context["source"] == "helium10_mcp"


def test_market_context_uses_fresh_keywords_and_optional_sales_benchmark(sync_client):
    client, _ = sync_client
    payload = helium_payload()
    litet = payload["brands"]["Litet"]
    litet["competitors"][0]["sales"] = None
    litet["sales_benchmark"] = {"monthly_sales": 164}
    response = client.put(
        "/admin/helium-snapshot",
        json=payload,
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200
    from decision_dashboard_v2.analytics import market_context
    context = market_context("Litet")
    assert context["competitor_sales_median"] == 164
    assert context["strategic_gaps"][0]["phrase"] == "cycling socks"
    assert context["strategic_gaps"][0]["rank"] == 12


def test_health_allows_initial_database_upload(tmp_path, monkeypatch):
    monkeypatch.setenv("LITET_DB_PATH", str(tmp_path / "not-created-yet.db"))
    from decision_dashboard_v2.app import app
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "initializing"


def test_health_allows_initial_variable_configuration(monkeypatch):
    monkeypatch.delenv("LITET_DB_PATH", raising=False)
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
