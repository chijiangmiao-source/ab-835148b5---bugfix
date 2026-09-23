"""API 端到端测试（TestClient）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_solve_ok():
    payload = {
        "points": ["r", "a", "b", "c", "d"],
        "root": "r",
        "channels": [
            {"id": "e1", "from": "r", "to": "a", "cost": 5},
            {"id": "e2", "from": "a", "to": "b", "cost": 1},
            {"id": "e3", "from": "b", "to": "a", "cost": 1},
            {"id": "e4", "from": "b", "to": "c", "cost": 1},
            {"id": "e5", "from": "c", "to": "a", "cost": 1},
            {"id": "e6", "from": "c", "to": "d", "cost": 1},
        ],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["total_cost"] == 8
    assert body["canonical_ids"] == ["e1", "e2", "e4", "e6"]
    assert len(body["tree"]) == 4
    assert body["record"]["contractions"] == 2
    assert len(body["record"]["expansions"]) == 2


def test_solve_double_cycle_evidence():
    """双零代价环：总代价/规范树不变，但记录须含两层收缩、三层选择、两次展开。"""
    payload = {
        "points": ["r", "a", "b", "c", "d"],
        "root": "r",
        "channels": [
            {"id": "e1", "from": "b", "to": "a", "cost": 0},
            {"id": "e2", "from": "a", "to": "b", "cost": 0},
            {"id": "e3", "from": "d", "to": "c", "cost": 0},
            {"id": "e4", "from": "c", "to": "d", "cost": 0},
            {"id": "e5", "from": "r", "to": "a", "cost": 2},
            {"id": "e6", "from": "r", "to": "c", "cost": 2},
            {"id": "e7", "from": "b", "to": "c", "cost": 1},
        ],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["total_cost"] == 3
    assert body["canonical_ids"] == ["e2", "e4", "e5", "e7"]
    rec = body["record"]
    assert rec["contractions"] == 2
    assert [lv["depth"] for lv in rec["levels"]] == [0, 1, 2]
    assert rec["levels"][0]["cycle"]["nodes"] == ["a", "b"]
    assert rec["levels"][1]["cycle"]["nodes"] == ["c", "d"]
    assert rec["levels"][2]["cycle"] is None
    assert len(rec["expansions"]) == 2
    assert rec["expansions"][0]["entering_channel"] == "e7"
    assert rec["expansions"][0]["removed_cycle_channel"] == "e3"
    assert rec["expansions"][1]["entering_channel"] == "e5"
    assert rec["expansions"][1]["removed_cycle_channel"] == "e1"
    # 通道录入乱序不影响结果
    shuffled = dict(payload)
    shuffled["channels"] = list(reversed(payload["channels"]))
    r2 = client.post("/api/solve", json=shuffled)
    assert r2.json()["record"] == rec


def test_solve_unsolvable():
    payload = {
        "points": ["r", "a", "z"],
        "root": "r",
        "channels": [{"id": "u1", "from": "r", "to": "a", "cost": 1}],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unsolvable"
    assert body["unreachable"] == ["z"]
    assert body["reason"]


def test_invalid_self_loop():
    payload = {
        "points": ["r", "a"],
        "root": "r",
        "channels": [{"id": "c1", "from": "a", "to": "a", "cost": 1}],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == "invalid"
    assert any("自环" in e for e in body["errors"])


def test_invalid_schema():
    r = client.post("/api/solve", json={"points": ["r"], "root": "r"})
    assert r.status_code == 422
    assert r.json()["status"] == "invalid"


def test_negative_cost_rejected():
    payload = {
        "points": ["r", "a"],
        "root": "r",
        "channels": [{"id": "c1", "from": "r", "to": "a", "cost": -2}],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 422
    assert r.json()["status"] == "invalid"
