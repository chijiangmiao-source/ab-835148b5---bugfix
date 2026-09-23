"""最小汇流树求解器单元测试。

包含与暴力枚举对拍的随机化测试：枚举所有 n-1 条边的子集，
独立验证最小总代价与字典序最小规范树。
"""

from __future__ import annotations

import copy
import itertools
import json
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

# 双零代价环：{a,b} 与 {c,d}，经 e7（b→c）串联，根入口 e5/e6 代价均为 2。
# 最优树代价 3：e5 打破第一环、e7 从第一环跨入第二环，环上各保留一条零代价边。
DOUBLE_CYCLE = (
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

ACYCLIC_CHAIN = (
    ["r", "a", "b", "c"],
    "r",
    make(
        ["r", "a", "b", "c"],
        "r",
        [("t1", "r", "a", 1), ("t2", "a", "b", 2), ("t3", "b", "c", 3)],
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


class TestDoubleCycle:
    """双零代价环（并列、经跨环通道串联）的完整证据链验收。"""

    def test_tree_and_cost(self):
        points, root, channels = DOUBLE_CYCLE
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 3
        assert res["canonical_ids"] == ["e2", "e4", "e5", "e7"]
        # 逐边合计与总代价一致
        assert sum(e["cost"] for e in res["tree"]) == 3
        by_id = {e["id"]: e for e in res["tree"]}
        assert [(by_id[c]["from"], by_id[c]["to"]) for c in res["canonical_ids"]] == [
            ("a", "b"), ("c", "d"), ("r", "a"), ("b", "c"),
        ]

    def test_record_three_levels_two_contractions(self):
        points, root, channels = DOUBLE_CYCLE
        rec = solve(points, root, channels)["record"]
        assert rec["contractions"] == 2
        assert len(rec["levels"]) == 3
        assert [lv["depth"] for lv in rec["levels"]] == [0, 1, 2]

        # 第 0 层：四个点全部选零代价入口，a/b 闭成环
        lv0 = rec["levels"][0]
        assert {c["channel"] for c in lv0["chosen"]} == {"e1", "e2", "e3", "e4"}
        cy0 = lv0["cycle"]
        assert set(cy0["nodes"]) == {"a", "b"}
        assert set(cy0["channels"]) == {"e1", "e2"}
        s1 = cy0["supernode"]
        # 环的入环候选：仅 e5（r→a，代价 2 − 0 = 2）
        assert {(r["channel"], r["adjusted_cost"], r["enters"])
                for r in cy0["rewired_in"]} == {("e5", 2, "a")}
        assert cy0["dropped_internal"] == []

        # 第 1 层：S1 选 e5；c/d 仍闭成零代价环
        lv1 = rec["levels"][1]
        assert lv1["nodes"] == sorted({"r", s1, "c", "d"})
        pick1 = {c["node"]: c["channel"] for c in lv1["chosen"]}
        assert pick1 == {s1: "e5", "c": "e3", "d": "e4"}
        cy1 = lv1["cycle"]
        assert set(cy1["nodes"]) == {"c", "d"}
        assert set(cy1["channels"]) == {"e3", "e4"}
        s2 = cy1["supernode"]
        assert s2 != s1
        # 入环候选：e6（r→c，修正 2）与 e7（S1→c，修正 1）
        assert {(r["channel"], r["adjusted_cost"], r["enters"])
                for r in cy1["rewired_in"]} == {("e6", 2, "c"), ("e7", 1, "c")}

        # 第 2 层（最深）：e5 进入第一个超点，e7 跨入第二个超点，无环
        lv2 = rec["levels"][2]
        assert lv2["cycle"] is None
        assert {c["node"]: c["channel"] for c in lv2["chosen"]} == {
            s1: "e5", s2: "e7",
        }

    def test_expansions_inner_first(self):
        points, root, channels = DOUBLE_CYCLE
        rec = solve(points, root, channels)["record"]
        s1 = rec["levels"][0]["cycle"]["supernode"]
        s2 = rec["levels"][1]["cycle"]["supernode"]
        exps = rec["expansions"]
        assert len(exps) == 2

        # 先展开内环 c/d：e7 进入 c，替掉 e3、保留 e4
        assert exps[0] == {
            "supernode": s2,
            "entering_channel": "e7",
            "enters_node": "c",
            "removed_cycle_channel": "e3",
            "kept_cycle_channels": ["e4"],
        }
        # 再展开外环 a/b：e5 进入 a，替掉 e1、保留 e2
        assert exps[1] == {
            "supernode": s1,
            "entering_channel": "e5",
            "enters_node": "a",
            "removed_cycle_channel": "e1",
            "kept_cycle_channels": ["e2"],
        }

    def test_replay_matches_tree(self):
        points, root, channels = DOUBLE_CYCLE
        res = solve(points, root, channels)
        assert replay_record(points, root, channels, res["record"]) == [
            "e2", "e4", "e5", "e7",
        ]

    def test_channel_order_invariance(self):
        points, root, channels = DOUBLE_CYCLE
        ref = solve(points, root, channels)
        ref_norm = json.dumps(ref["record"], sort_keys=True, ensure_ascii=False)
        rng = random.Random(20260923)
        for _ in range(30):
            shuffled = channels[:]
            rng.shuffle(shuffled)
            got = solve(points, root, shuffled)
            assert got["canonical_ids"] == ref["canonical_ids"]
            assert got["total_cost"] == ref["total_cost"]
            assert json.dumps(got["record"], sort_keys=True, ensure_ascii=False) == ref_norm

    def test_forged_single_level_record_rejected(self):
        """旧缺陷形态：把最终树伪装成唯一的无环第 0 层，独立复算必须拒绝。"""
        points, root, channels = DOUBLE_CYCLE
        forged = {
            "levels": [
                {
                    "depth": 0,
                    "nodes": sorted(points),
                    "chosen": [
                        {"node": "a", "channel": "e5", "cost": 2},
                        {"node": "b", "channel": "e2", "cost": 0},
                        {"node": "c", "channel": "e7", "cost": 1},
                        {"node": "d", "channel": "e4", "cost": 0},
                    ],
                    "cycle": None,
                }
            ],
            "expansions": [],
            "contractions": 0,
        }
        with pytest.raises(AssertionError):
            replay_record(points, root, channels, forged)

    @pytest.mark.parametrize(
        "mutate",
        [
            # 删掉一次收缩（最深层前移并漏报第 1 层的环）
            lambda r: r["levels"].pop(1),
            # 抹掉第 0 层的环
            lambda r: r["levels"][0].__setitem__("cycle", None),
            # 展开次序颠倒（先外后内）
            lambda r: r["expansions"].reverse(),
            # 篡改被替换环边（e7 展开时伪称替掉 e4）
            lambda r: r["expansions"][0].__setitem__(
                "removed_cycle_channel", "e4"
            ),
            # 篡改修正代价
            lambda r: r["levels"][1]["cycle"]["rewired_in"][1].__setitem__(
                "adjusted_cost", 0
            ),
            # contractions 计数与层数不符
            lambda r: r.__setitem__("contractions", 1),
        ],
    )
    def test_tampered_records_rejected(self, mutate):
        points, root, channels = DOUBLE_CYCLE
        rec = copy.deepcopy(solve(points, root, channels)["record"])
        mutate(rec)
        with pytest.raises(AssertionError):
            replay_record(points, root, channels, rec)


class TestAcyclic:
    def test_chain_has_zero_contractions_single_level(self):
        points, root, channels = ACYCLIC_CHAIN
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 6
        assert res["canonical_ids"] == ["t1", "t2", "t3"]
        rec = res["record"]
        assert rec["contractions"] == 0
        assert len(rec["levels"]) == 1
        assert rec["levels"][0]["depth"] == 0
        assert rec["levels"][0]["cycle"] is None
        assert rec["expansions"] == []
        assert replay_record(points, root, channels, rec) == ["t1", "t2", "t3"]


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
