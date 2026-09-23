"""最小汇流树求解器单元测试。

包含与暴力枚举对拍的随机化测试：枚举所有 n-1 条边的子集，
独立验证最小总代价与字典序最小规范树。
"""

from __future__ import annotations

import itertools
import random

import pytest

from app.arborescence import (
    Channel,
    ProblemError,
    reachable_from,
    replay_record,
    solve,
    validate_problem,
)


def brute_force(points, root, channels):
    """暴力枚举全部 n-1 边子集，返回 (最小代价, 字典序最小标识序列) 或 None。"""
    n = len(points)
    best_cost = None
    best_ids = None
    for combo in itertools.combinations(channels, n - 1):
        indeg = {}
        ok = True
        for c in combo:
            if c.v == root:
                ok = False
                break
            indeg[c.v] = indeg.get(c.v, 0) + 1
            if indeg[c.v] > 1:
                ok = False
                break
        if not ok or any(indeg.get(p, 0) != 1 for p in points if p != root):
            continue
        if reachable_from(root, list(combo)) != set(points):
            continue
        cost = sum(c.cost for c in combo)
        ids = sorted(c.id for c in combo)
        if best_cost is None or cost < best_cost or (cost == best_cost and ids < best_ids):
            best_cost, best_ids = cost, ids
    if best_cost is None:
        return None
    return best_cost, best_ids


def make(points, root, channels):
    return [Channel(id=c[0], u=c[1], v=c[2], cost=c[3]) for c in channels]


NESTED = (
    ["r", "a", "b", "c", "d"],
    "r",
    make(
        ["r", "a", "b", "c", "d"],
        "r",
        [
            ("e1", "r", "a", 5),
            ("e2", "a", "b", 1),
            ("e3", "b", "a", 1),
            ("e4", "b", "c", 1),
            ("e5", "c", "a", 1),
            ("e6", "c", "d", 1),
        ],
    ),
)

PARALLEL = (
    ["r", "x", "y"],
    "r",
    make(
        ["r", "x", "y"],
        "r",
        [
            ("p1", "r", "x", 3),
            ("p2", "r", "x", 1),
            ("p3", "x", "y", 2),
            ("p4", "r", "y", 9),
            ("p5", "y", "x", 4),
        ],
    ),
)

CANONICAL = (
    ["r", "b", "c", "d"],
    "r",
    make(
        ["r", "b", "c", "d"],
        "r",
        [
            ("k1", "r", "b", 1),
            ("k2", "b", "c", 1),
            ("k3", "r", "c", 1),
            ("k4", "c", "d", 1),
            ("k5", "r", "d", 1),
        ],
    ),
)

UNREACHABLE = (
    ["r", "a", "b", "z"],
    "r",
    make(
        ["r", "a", "b", "z"],
        "r",
        [("u1", "r", "a", 1), ("u2", "a", "b", 1), ("u3", "z", "a", 1)],
    ),
)

# 双零代价环：{a,b} 与 {c,d} 各自成环，需两次收缩；
# 规范树 [e2, e4, e5, e7]，总代价 3。
DUAL_RING = (
    ["r", "a", "b", "c", "d"],
    "r",
    make(
        ["r", "a", "b", "c", "d"],
        "r",
        [
            ("e1", "b", "a", 0),
            ("e2", "a", "b", 0),
            ("e3", "d", "c", 0),
            ("e4", "c", "d", 0),
            ("e5", "r", "a", 2),
            ("e6", "r", "c", 2),
            ("e7", "b", "c", 1),
        ],
    ),
)


class TestSamples:
    def test_nested_cycles(self):
        points, root, channels = NESTED
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 8
        assert res["canonical_ids"] == ["e1", "e2", "e4", "e6"]
        levels = res["record"]["levels"]
        # 第一层收缩环 {a, b}
        assert levels[0]["cycle"] is not None
        assert set(levels[0]["cycle"]["nodes"]) == {"a", "b"}
        s1 = levels[0]["cycle"]["supernode"]
        # 第二层出现嵌套环：超点 S1 与 c 互指
        assert levels[1]["cycle"] is not None
        assert set(levels[1]["cycle"]["nodes"]) == {s1, "c"}
        assert res["record"]["contractions"] == 2
        # 展开记录：先内层后外层
        exps = res["record"]["expansions"]
        assert len(exps) == 2
        assert exps[0]["entering_channel"] == "e1"
        assert exps[0]["removed_cycle_channel"] == "e5"
        assert exps[1]["removed_cycle_channel"] == "e3"
        # 记录可复算
        assert replay_record(points, root, channels, res["record"]) == res["canonical_ids"]

    def test_parallel_channels(self):
        points, root, channels = PARALLEL
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 3
        assert res["canonical_ids"] == ["p2", "p3"]
        assert res["record"]["contractions"] == 0
        assert replay_record(points, root, channels, res["record"]) == ["p2", "p3"]

    def test_canonical_tiebreak(self):
        points, root, channels = CANONICAL
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 3
        # 四棵同优树中字典序最小者为 [k1, k2, k4]
        assert res["canonical_ids"] == ["k1", "k2", "k4"]
        assert replay_record(points, root, channels, res["record"]) == ["k1", "k2", "k4"]

    def test_unreachable(self):
        points, root, channels = UNREACHABLE
        res = solve(points, root, channels)
        assert res["status"] == "unsolvable"
        assert res["unreachable"] == ["z"]
        assert res["reason"]


class TestDualRing:
    """双零代价环场景：两次收缩、三个层级、两次展开，证据链与结果一致。"""

    def test_dual_zero_cost_cycles(self):
        points, root, channels = DUAL_RING
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        # 规范树与总代价不受记录修复影响
        assert res["total_cost"] == 3
        assert res["canonical_ids"] == ["e2", "e4", "e5", "e7"]
        assert sum(e["cost"] for e in res["tree"]) == 3

        record = res["record"]
        assert record["contractions"] == 2
        levels = record["levels"]
        assert [lv["depth"] for lv in levels] == [0, 1, 2]

        # 第 0 层先显示 a、b 的零代价环
        cyc0 = levels[0]["cycle"]
        assert cyc0 is not None
        assert set(cyc0["nodes"]) == {"a", "b"}
        assert set(cyc0["channels"]) == {"e1", "e2"}
        s1 = cyc0["supernode"]
        # 第 0 层各点最低入口恰为四条零代价环边
        assert {c["node"]: c["channel"] for c in levels[0]["chosen"]} == {
            "a": "e1",
            "b": "e2",
            "c": "e3",
            "d": "e4",
        }

        # 第 1 层再显示 c、d 的零代价环
        cyc1 = levels[1]["cycle"]
        assert cyc1 is not None
        assert set(cyc1["nodes"]) == {"c", "d"}
        assert set(cyc1["channels"]) == {"e3", "e4"}
        s2 = cyc1["supernode"]
        assert s1 != s2

        # 最深层（叶层）无环：e5 进入第一个超点、e7 进入第二个超点
        leaf = levels[2]
        assert leaf["cycle"] is None
        assert {c["node"]: c["channel"] for c in leaf["chosen"]} == {s1: "e5", s2: "e7"}

        # 两次展开与两个收缩超点一一对应，深层先展开
        exps = record["expansions"]
        assert len(exps) == 2
        assert [e["supernode"] for e in exps] == [s2, s1]
        # 先由 e7 进入 c、替换 e3、保留 e4
        assert exps[0]["entering_channel"] == "e7"
        assert exps[0]["enters_node"] == "c"
        assert exps[0]["removed_cycle_channel"] == "e3"
        assert exps[0]["kept_cycle_channels"] == ["e4"]
        # 再由 e5 进入 a、替换 e1、保留 e2
        assert exps[1]["entering_channel"] == "e5"
        assert exps[1]["enters_node"] == "a"
        assert exps[1]["removed_cycle_channel"] == "e1"
        assert exps[1]["kept_cycle_channels"] == ["e2"]

        # 证据链复算：叶层入选 ∪ 展开保留 = 规范树，逐边合计 = 总代价
        by_id = {c.id: c for c in channels}
        evidence_ids = {c["channel"] for c in leaf["chosen"]}
        evidence_cost = sum(c["cost"] for c in leaf["chosen"])
        for e in exps:
            evidence_ids.update(e["kept_cycle_channels"])
            evidence_cost += sum(by_id[k].cost for k in e["kept_cycle_channels"])
        assert sorted(evidence_ids) == res["canonical_ids"]
        assert evidence_cost == res["total_cost"]

        # 独立记录复算得到同一规范树
        assert replay_record(points, root, channels, record) == res["canonical_ids"]

    def test_channel_order_irrelevant(self):
        # 调整通道录入顺序，求解结果与可复算记录完全一致
        points, root, channels = DUAL_RING
        base = solve(points, root, channels)
        assert base["status"] == "ok"
        rng = random.Random(20260923)
        for _ in range(20):
            shuffled = list(channels)
            rng.shuffle(shuffled)
            assert solve(points, root, shuffled) == base
        # 逆序亦同
        assert solve(points, root, list(reversed(channels))) == base

    def test_acyclic_chain_keeps_zero_contractions(self):
        # 无环链路：单次无环层级、零收缩、无展开
        points = ["r", "a", "b", "c"]
        channels = make(
            points,
            "r",
            [("c1", "r", "a", 2), ("c2", "a", "b", 1), ("c3", "b", "c", 3)],
        )
        res = solve(points, "r", channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 6
        assert res["canonical_ids"] == ["c1", "c2", "c3"]
        record = res["record"]
        assert record["contractions"] == 0
        assert record["expansions"] == []
        assert len(record["levels"]) == 1
        assert record["levels"][0]["cycle"] is None
        assert replay_record(points, "r", channels, record) == res["canonical_ids"]


class TestValidation:
    def ok(self, points, root, channels):
        validate_problem(points, root, make(points, root, channels))

    def test_too_few_points(self):
        with pytest.raises(ProblemError):
            self.ok(["r"], "r", [])

    def test_too_many_points(self):
        with pytest.raises(ProblemError):
            self.ok([f"p{i}" for i in range(41)], "p0", [])

    def test_duplicate_point(self):
        with pytest.raises(ProblemError) as ei:
            self.ok(["r", "a", "a"], "r", [])
        assert any("重复" in e for e in ei.value.errors)

    def test_root_not_in_points(self):
        with pytest.raises(ProblemError):
            self.ok(["r", "a"], "x", [("c1", "r", "a", 1)])

    def test_self_loop(self):
        with pytest.raises(ProblemError) as ei:
            self.ok(["r", "a"], "r", [("c1", "a", "a", 1)])
        assert any("自环" in e for e in ei.value.errors)

    def test_duplicate_channel_id(self):
        with pytest.raises(ProblemError):
            self.ok(["r", "a"], "r", [("c1", "r", "a", 1), ("c1", "r", "a", 2)])

    def test_negative_cost(self):
        with pytest.raises(ProblemError):
            self.ok(["r", "a"], "r", [("c1", "r", "a", -1)])

    def test_too_many_channels(self):
        chans = [(f"c{i}", "r", "a", 1) for i in range(161)]
        with pytest.raises(ProblemError):
            self.ok(["r", "a"], "r", chans)

    def test_parallel_allowed(self):
        self.ok(["r", "a"], "r", [("c1", "r", "a", 1), ("c2", "r", "a", 5)])

    def test_non_ascii_id_rejected(self):
        with pytest.raises(ProblemError):
            self.ok(["r", "点"], "r", [])


class TestStructure:
    def test_supernode_name_collision_avoided(self):
        # 用户点占用了 S1，超点须另取名字
        points = ["r", "S1", "b"]
        channels = make(
            points,
            "r",
            [("c1", "r", "S1", 5), ("c2", "S1", "b", 1), ("c3", "b", "S1", 1)],
        )
        res = solve(points, "r", channels)
        assert res["status"] == "ok"
        assert res["canonical_ids"] == ["c1", "c2"]
        sname = res["record"]["levels"][0]["cycle"]["supernode"]
        assert sname != "S1"

    def test_edge_into_root_never_selected(self):
        points = ["r", "a"]
        channels = make(points, "r", [("c1", "r", "a", 1), ("c2", "a", "r", 0)])
        res = solve(points, "r", channels)
        assert res["canonical_ids"] == ["c1"]

    def test_zero_cost_cycle(self):
        points = ["r", "a", "b"]
        channels = make(
            points,
            "r",
            [("c1", "r", "a", 0), ("c2", "a", "b", 0), ("c3", "b", "a", 0)],
        )
        res = solve(points, "r", channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 0

    def test_chain_of_40(self):
        points = [f"n{i:02d}" for i in range(40)]
        channels = make(
            points, "n00", [(f"c{i:02d}", f"n{i:02d}", f"n{i+1:02d}", i) for i in range(39)]
        )
        res = solve(points, "n00", channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == sum(range(39))
        assert len(res["canonical_ids"]) == 39


class TestBruteForce:
    @pytest.mark.parametrize("seed", range(300))
    def test_random_small(self, seed):
        rng = random.Random(seed)
        n = rng.randint(2, 6)
        points = [f"v{i}" for i in range(n)]
        root = points[0]
        m = rng.randint(0, min(12, n * (n - 1)))
        pairs = [(u, v) for u in points for v in points if u != v]
        rng.shuffle(pairs)
        channels = [
            Channel(id=f"e{i}", u=u, v=v, cost=rng.randint(0, 5))
            for i, (u, v) in enumerate(pairs[:m])
        ]
        res = solve(points, root, channels)
        expect = brute_force(points, root, channels)
        if expect is None:
            assert res["status"] == "unsolvable"
            assert res["unreachable"]
        else:
            assert res["status"] == "ok"
            assert res["total_cost"] == expect[0]
            assert res["canonical_ids"] == expect[1]
            assert replay_record(points, root, channels, res["record"]) == expect[1]

    def test_random_with_parallel_edges(self):
        rng = random.Random(20260922)
        for _ in range(200):
            n = rng.randint(2, 5)
            points = [f"v{i}" for i in range(n)]
            root = points[0]
            m = rng.randint(0, 14)
            channels = []
            for i in range(m):
                u = rng.choice(points)
                v = rng.choice([p for p in points if p != u])
                channels.append(Channel(id=f"e{i}", u=u, v=v, cost=rng.randint(0, 4)))
            res = solve(points, root, channels)
            expect = brute_force(points, root, channels)
            if expect is None:
                assert res["status"] == "unsolvable"
            else:
                assert res["status"] == "ok"
                assert res["total_cost"] == expect[0]
                assert res["canonical_ids"] == expect[1]
                assert replay_record(points, root, channels, res["record"]) == expect[1]
