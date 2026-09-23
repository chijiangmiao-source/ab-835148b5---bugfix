"""verify 一次性服务：对真实 API 与经 Web 反代的同一请求做样例核对 + HTTP 冒烟。

样例覆盖：嵌套环收缩、平行通道、同优规范树字典序、不可达点；
另含输入错误（自环 / 结构非法）核对。全部断言通过则进程以 0 退出，
任一失败立即以非零码退出。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

# 复用后端的记录复算逻辑，从“独立消费者”视角核对可复算记录
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/srv/api")
sys.path.insert(0, os.path.join(_HERE, "..", "api"))
from app.arborescence import Channel, replay_record  # noqa: E402

API = os.environ.get("API_BASE", "http://api:8000")
WEB = os.environ.get("WEB_BASE", "http://web")

FAILURES: list[str] = []


def http(method: str, url: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def wait_for(url: str, label: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1)
    FAILURES.append(f"{label} 在 {timeout}s 内未就绪: {last}")
    return False


def check(cond: bool, msg: str) -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {msg}")
    if not cond:
        FAILURES.append(msg)


def channels_of(payload: dict) -> list[Channel]:
    return [
        Channel(id=c["id"], u=c["from"], v=c["to"], cost=c["cost"])
        for c in payload["channels"]
    ]


SCENARIOS = {
    "nested": {
        "payload": {
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
        },
        "expect_ids": ["e1", "e2", "e4", "e6"],
        "expect_cost": 8,
        "expect_contractions": 2,
        "expect_level_count": 3,
        "expect_cycle_nodes": [{"a", "b"}, {"S1", "c"}],
        "expect_expansions": [
            {"entering": "e1", "removed": "e5"},
            {"entering": "e1", "removed": "e3"},
        ],
    },
    "double": {
        "payload": {
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
        },
        "expect_ids": ["e2", "e4", "e5", "e7"],
        "expect_cost": 3,
        "expect_contractions": 2,
        "expect_level_count": 3,
        "expect_cycle_nodes": [{"a", "b"}, {"c", "d"}],
        "expect_expansions": [
            {"entering": "e7", "removed": "e3", "kept": ["e4"]},
            {"entering": "e5", "removed": "e1", "kept": ["e2"]},
        ],
    },
    "acyclic": {
        "payload": {
            "points": ["r", "a", "b", "c"],
            "root": "r",
            "channels": [
                {"id": "t1", "from": "r", "to": "a", "cost": 1},
                {"id": "t2", "from": "a", "to": "b", "cost": 2},
                {"id": "t3", "from": "b", "to": "c", "cost": 3},
            ],
        },
        "expect_ids": ["t1", "t2", "t3"],
        "expect_cost": 6,
        "expect_contractions": 0,
        "expect_level_count": 1,
        "expect_expansions": [],
    },
    "parallel": {
        "payload": {
            "points": ["r", "x", "y"],
            "root": "r",
            "channels": [
                {"id": "p1", "from": "r", "to": "x", "cost": 3},
                {"id": "p2", "from": "r", "to": "x", "cost": 1},
                {"id": "p3", "from": "x", "to": "y", "cost": 2},
                {"id": "p4", "from": "r", "to": "y", "cost": 9},
                {"id": "p5", "from": "y", "to": "x", "cost": 4},
            ],
        },
        "expect_ids": ["p2", "p3"],
        "expect_cost": 3,
        "expect_contractions": 0,
    },
    "canonical": {
        "payload": {
            "points": ["r", "b", "c", "d"],
            "root": "r",
            "channels": [
                {"id": "k1", "from": "r", "to": "b", "cost": 1},
                {"id": "k2", "from": "b", "to": "c", "cost": 1},
                {"id": "k3", "from": "r", "to": "c", "cost": 1},
                {"id": "k4", "from": "c", "to": "d", "cost": 1},
                {"id": "k5", "from": "r", "to": "d", "cost": 1},
            ],
        },
        "expect_ids": ["k1", "k2", "k4"],
        "expect_cost": 3,
        "expect_contractions": 0,
    },
    "unreachable": {
        "payload": {
            "points": ["r", "a", "b", "z"],
            "root": "r",
            "channels": [
                {"id": "u1", "from": "r", "to": "a", "cost": 1},
                {"id": "u2", "from": "a", "to": "b", "cost": 1},
                {"id": "u3", "from": "z", "to": "a", "cost": 1},
            ],
        },
        "expect_unreachable": ["z"],
    },
}


def verify_ok_scenario(name: str, sc: dict) -> None:
    print(f"- 样例 {name}")
    st_api, body_api = http("POST", f"{API}/api/solve", sc["payload"])
    st_web, body_web = http("POST", f"{WEB}/api/solve", sc["payload"])
    check(st_api == 200 and body_api.get("status") == "ok", "API 直连返回 200/ok")
    check(st_web == 200 and body_web.get("status") == "ok", "经页面同源反代返回 200/ok")
    check(body_api == body_web, "页面反代结果与 API 直连完全一致")
    if body_api.get("status") != "ok":
        return
    check(body_api["total_cost"] == sc["expect_cost"],
          f"总代价 == {sc['expect_cost']}（实际 {body_api['total_cost']}）")
    check(body_api["canonical_ids"] == sc["expect_ids"],
          f"规范树标识序列 == {sc['expect_ids']}（实际 {body_api['canonical_ids']}）")
    rec = body_api["record"]
    check(rec["contractions"] == sc["expect_contractions"],
          f"环收缩次数 == {sc['expect_contractions']}（实际 {rec['contractions']}）")

    # 计算层级：深度连续、最深层无环
    levels = rec["levels"]
    expect_levels = sc.get("expect_level_count", 1)
    check(len(levels) == expect_levels,
          f"计算层级数 == {expect_levels}（实际 {len(levels)}）")
    check([lv["depth"] for lv in levels] == list(range(len(levels))), "层级深度连续 0..N")
    check(levels[-1]["cycle"] is None, "最深层无环")

    # 各收缩层的环节点集合，以及两条展开记录与收缩超点一一对应
    cycle_levels = [lv for lv in levels if lv["cycle"] is not None]
    got_cycle_sets = [set(lv["cycle"]["nodes"]) for lv in cycle_levels]
    expect_cycles = sc.get("expect_cycle_nodes", [])
    check(got_cycle_sets == expect_cycles,
          f"各环节点集合 == {[set(s) for s in expect_cycles]}（实际 {got_cycle_sets}）")
    exps = rec["expansions"]
    check(len(exps) == sc["expect_contractions"], "展开记录数 == 收缩次数")
    super_pairs = list(zip(
        [lv["cycle"]["supernode"] for lv in cycle_levels],
        [e["supernode"] for e in reversed(exps)],
    ))
    check(all(a == b for a, b in super_pairs), "每条展开对应一个收缩超点（先内后外）")
    for i, want in enumerate(sc.get("expect_expansions", [])):
        got = exps[i]
        check(got["entering_channel"] == want["entering"]
              and got["removed_cycle_channel"] == want["removed"],
              f"展开 {i+1}：{want['entering']} 进入并替换 {want['removed']}"
              f"（实际 {got['entering_channel']} 替换 {got['removed_cycle_channel']}）")
        if "kept" in want:
            check(got["kept_cycle_channels"] == want["kept"],
                  f"展开 {i+1} 保留环边 == {want['kept']}"
                  f"（实际 {got['kept_cycle_channels']}）")

    replayed = replay_record(
        sc["payload"]["points"], sc["payload"]["root"],
        channels_of(sc["payload"]), rec,
    )
    check(replayed == body_api["canonical_ids"], "收缩/展开记录独立复算得到同一规范树")
    cost_sum = sum(
        c["cost"] for c in body_api["tree"] if c["id"] in set(body_api["canonical_ids"])
    )
    check(cost_sum == body_api["total_cost"], "逐边代价之和等于总代价")

    # 通道录入乱序：规范树与全部证据记录保持不变（页面与 API 同源都核对）
    shuffled = dict(sc["payload"])
    shuffled["channels"] = list(reversed(sc["payload"]["channels"]))
    st_sh, body_sh = http("POST", f"{API}/api/solve", shuffled)
    st_shw, body_shw = http("POST", f"{WEB}/api/solve", shuffled)
    check(st_sh == 200 and body_sh.get("status") == "ok", "乱序通道 API 返回 200/ok")
    check(st_shw == 200 and body_shw == body_api, "乱序通道经页面反代结果与正序完全一致")
    check(body_sh == body_api, "通道录入顺序调整后总代价、规范树与证据记录均不变")
    replay_shuffled = replay_record(
        shuffled["points"], shuffled["root"], channels_of(shuffled), body_sh["record"],
    )
    check(replay_shuffled == body_api["canonical_ids"], "乱序记录独立复算仍得同一规范树")


def verify_unreachable_scenario() -> None:
    print("- 样例 unreachable（不可达点）")
    sc = SCENARIOS["unreachable"]
    st_api, body_api = http("POST", f"{API}/api/solve", sc["payload"])
    st_web, body_web = http("POST", f"{WEB}/api/solve", sc["payload"])
    check(st_api == 200 and body_api["status"] == "unsolvable", "API 直连报告无解")
    check(body_web == body_api, "页面反代同样报告无解")
    check(body_api["unreachable"] == sc["expect_unreachable"],
          f"不可达点 == {sc['expect_unreachable']}（实际 {body_api['unreachable']}）")
    check(bool(body_api.get("reason")), "附带明确原因说明")


def verify_invalid_inputs() -> None:
    print("- 输入错误核对")
    # 自环
    self_loop = {
        "points": ["r", "a"], "root": "r",
        "channels": [{"id": "c1", "from": "a", "to": "a", "cost": 1}],
    }
    st, body = http("POST", f"{API}/api/solve", self_loop)
    check(st == 422 and body["status"] == "invalid", "自环返回 422/invalid")
    check(any("自环" in e for e in body.get("errors", [])), "自环原因明确")
    st2, body2 = http("POST", f"{WEB}/api/solve", self_loop)
    check(st2 == 422 and body2["status"] == "invalid", "页面反代同样拒绝自环")
    # 结构非法（根不在点集 + 点不足）
    bad = {"points": ["x"], "root": "nope", "channels": []}
    st, body = http("POST", f"{API}/api/solve", bad)
    check(st == 422 and body["status"] == "invalid", "结构非法返回 422/invalid")
    check(bool(body.get("errors")), "结构非法附带错误列表")
    # 负代价（pydantic 层）
    neg = {
        "points": ["r", "a"], "root": "r",
        "channels": [{"id": "c1", "from": "r", "to": "a", "cost": -3}],
    }
    st, body = http("POST", f"{API}/api/solve", neg)
    check(st == 422 and body["status"] == "invalid", "负代价返回 422/invalid")


def verify_http_smoke() -> None:
    print("- HTTP / 页面冒烟")
    for base, label in ((API, "API"), (WEB, "Web")):
        st, body = http("GET", f"{base}/api/health")
        check(st == 200 and body.get("status") == "ok", f"{label} 的 /api/health 可用")
    with urllib.request.urlopen(f"{WEB}/", timeout=5) as resp:
        html = resp.read().decode()
        check(resp.status == 200, "Web 首页 200")
        check('<div id="root">' in html, "首页包含 React 挂载点")
        check("/assets/" in html and html.count("<script") >= 1, "首页引用构建产物")


def main() -> int:
    print("== 等待服务就绪 ==")
    ok_api = wait_for(f"{API}/api/health", "api")
    ok_web = wait_for(f"{WEB}/", "web")
    if not (ok_api and ok_web):
        print("\nVERIFY FAILED:", "; ".join(FAILURES))
        return 1

    print("== 真实 API 与页面结果核对 ==")
    for name in ("nested", "double", "acyclic", "parallel", "canonical"):
        verify_ok_scenario(name, SCENARIOS[name])
    verify_unreachable_scenario()
    verify_invalid_inputs()
    verify_http_smoke()

    if FAILURES:
        print(f"\nVERIFY FAILED（{len(FAILURES)} 项）:")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("\nVERIFY PASSED：全部样例、记录复算、输入错误与冒烟检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
