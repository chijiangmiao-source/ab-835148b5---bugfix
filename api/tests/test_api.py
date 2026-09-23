"""API 端到端测试（TestClient）。"""

from __future__ import annotations

import random

from fastapi.testclient import TestClient

from app.arborescence import Channel, replay_record
from app.main import app

client = TestClient(app)

# 双零代价环：{a,b}、{c,d} 各一环，规范树 [e2, e4, e5, e7]，总代价 3
DUAL_RING_PAYLOAD = {
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


def test_solve_dual_zero_cost_cycles():
    r = client.post("/api/solve", json=DUAL_RING_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["total_cost"] == 3
    assert body["canonical_ids"] == ["e2", "e4", "e5", "e7"]
    assert sum(e["cost"] for e in body["tree"]) == body["total_cost"]

    record = body["record"]
    # 两次收缩、三个计算层级、两次展开
    assert record["contractions"] == 2
    levels = record["levels"]
    assert len(levels) == 3
    assert [lv["depth"] for lv in levels] == [0, 1, 2]
    assert set(levels[0]["cycle"]["nodes"]) == {"a", "b"}
    assert set(levels[1]["cycle"]["nodes"]) == {"c", "d"}
    assert levels[2]["cycle"] is None
    # 展开记录一一对应到收缩超点
    supers = [lv["cycle"]["supernode"] for lv in levels if lv["cycle"]]
    exps = record["expansions"]
    assert len(exps) == 2
    assert sorted(e["supernode"] for e in exps) == sorted(supers)
    # 独立记录复算得到同一规范树
    channels = [
        Channel(id=c["id"], u=c["from"], v=c["to"], cost=c["cost"])
        for c in DUAL_RING_PAYLOAD["channels"]
    ]
    assert (
        replay_record(DUAL_RING_PAYLOAD["points"], "r", channels, record)
        == body["canonical_ids"]
    )


def test_solve_dual_ring_channel_order_irrelevant():
    r = client.post("/api/solve", json=DUAL_RING_PAYLOAD)
    assert r.status_code == 200
    base = r.json()
    rng = random.Random(20260923)
    for _ in range(10):
        shuffled = dict(DUAL_RING_PAYLOAD)
        shuffled["channels"] = list(DUAL_RING_PAYLOAD["channels"])
        rng.shuffle(shuffled["channels"])
        r2 = client.post("/api/solve", json=shuffled)
        assert r2.status_code == 200
        assert r2.json() == base


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
