"""最小汇流树（最小树形图）求解器 —— Chu–Liu/Edmonds 算法的手工实现。

不依赖任何现成图优化库。给定注入根与带非负整数代价的有向通道，
求一棵以根为源、覆盖全部采样点、总代价最小的汇流树（每个非根点
恰有一条入选通道且自根可达）。同优解中按"升序通道标识序列"取字典序
最小者（规范树）。

除规范树外，本模块还产出可复算的有向环收缩 / 展开记录：
  * 每一层为每个非根点选出的最小入边；
  * 每次有向环收缩（环节点、环边、超点编号、入边代价修正、被丢弃的环内边）；
  * 每次展开替换（进入通道、进入点、被替换的环边、保留的环边）。

规范树的求得分两步：
  1. 用 Edmonds 求出最小总代价 C*；
  2. 按通道标识升序逐个尝试"强制入选"：若强制后仍存在代价为 C* 的
     汇流树，则强制之。可证明最终强制集本身就是字典序最小的最优树。
最后用 (代价, 是否规范边, 标识) 作为字典序边键再跑一次 Edmonds，
保证产出的收缩记录恰好对应规范树。
"""

from __future__ import annotations

from dataclasses import dataclass


class ProblemError(Exception):
    """输入不合法时抛出。errors 为逐条原因列表。"""

    def __init__(self, reason: str, errors: list[str] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.errors = errors or [reason]


@dataclass(frozen=True)
class Channel:
    id: str
    u: str  # 上游点（from）
    v: str  # 下游点（to）
    cost: int


@dataclass
class _Edge:
    """某一收缩层级上的边。orig 始终指向原始通道。"""

    orig: Channel
    u: str  # 当前层级的尾点（可能是超点）
    v: str  # 当前层级的头点（可能是超点）
    key: tuple  # 字典序键 (代价, 惩罚, 标识)
    enters: str  # 在当前层级上本边进入的节点（== v，展开时用来定位环边）
    lower: "_Edge | None"  # 收缩前一层对应的边；原始层为 None


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------

_MAX_POINTS = 40
_MIN_POINTS = 2
_MAX_CHANNELS = 160
_MAX_ID_LEN = 32


def _is_ascii_id(value: str) -> bool:
    if not isinstance(value, str) or not (1 <= len(value) <= _MAX_ID_LEN):
        return False
    # 可打印 ASCII（不含空白），便于排序与展示
    return all(0x21 <= ord(ch) <= 0x7E for ch in value)


def validate_problem(
    points: list[str], root: str, channels: list[Channel]
) -> None:
    """收集全部输入错误；有任何错误即抛 ProblemError。"""
    errors: list[str] = []

    if not (_MIN_POINTS <= len(points) <= _MAX_POINTS):
        errors.append(
            f"采样点数量须为 {_MIN_POINTS}..{_MAX_POINTS}，实际为 {len(points)}"
        )
    seen: set[str] = set()
    for p in points:
        if not _is_ascii_id(p):
            errors.append(f"采样点标识非法（须为 1..{_MAX_ID_LEN} 个可打印 ASCII 字符）: {p!r}")
        elif p in seen:
            errors.append(f"采样点标识重复: {p!r}")
        seen.add(p)

    if not _is_ascii_id(root):
        errors.append(f"注入根标识非法: {root!r}")
    elif root not in seen:
        errors.append(f"注入根 {root!r} 不在采样点集合中")

    if len(channels) > _MAX_CHANNELS:
        errors.append(f"通道数量至多为 {_MAX_CHANNELS}，实际为 {len(channels)}")

    chan_ids: set[str] = set()
    for c in channels:
        if not _is_ascii_id(c.id):
            errors.append(f"通道标识非法: {c.id!r}")
        elif c.id in chan_ids:
            errors.append(f"通道标识重复: {c.id!r}")
        chan_ids.add(c.id)
        if c.u not in seen:
            errors.append(f"通道 {c.id!r} 的起点 {c.u!r} 不是已知采样点")
        if c.v not in seen:
            errors.append(f"通道 {c.id!r} 的终点 {c.v!r} 不是已知采样点")
        if c.u == c.v:
            errors.append(f"通道 {c.id!r} 是自环（{c.u!r} -> {c.v!r}），不被允许")
        if not isinstance(c.cost, int) or isinstance(c.cost, bool) or c.cost < 0:
            errors.append(f"通道 {c.id!r} 的代价须为非负整数，实际为 {c.cost!r}")

    if errors:
        raise ProblemError("输入不合法", errors)


# ---------------------------------------------------------------------------
# Edmonds 核心（带收缩 / 展开记录）
# ---------------------------------------------------------------------------


def _fresh_supernode(idx: int, used: set[str]) -> str:
    name = f"S{idx}"
    n = idx
    while name in used:
        n += 1
        name = f"S{n}"
    return name


def _find_cycle(nodes: list[str], root: str, in_edge: dict[str, _Edge]) -> list[str] | None:
    """在每个非根点恰有一条选中入边的函数图上找一个有向环。

    返回环节点列表（沿选中入边逆向行走的顺序），无环返回 None。
    """
    for start in sorted(nodes):
        if start == root:
            continue
        seen: dict[str, int] = {}
        order: list[str] = []
        cur = start
        while cur != root and cur not in seen:
            seen[cur] = len(order)
            order.append(cur)
            cur = in_edge[cur].u
        if cur != root:
            return order[seen[cur]:]
    return None


def _cycle_forward(cycle: list[str], in_edge: dict[str, _Edge]) -> tuple[list[str], list[str]]:
    """把逆向行走得到的环转换为沿通道方向的展示顺序。

    返回 (节点序列, 通道标识序列)，其中通道 i 从节点 i 指向节点 i+1（末位回绕）。
    """
    # cycle 中 in_edge[cycle[i]].u == cycle[(i+1) % k]
    k = len(cycle)
    nodes_fwd = [cycle[0]] + [cycle[k - 1 - i] for i in range(k - 1)]
    channels_fwd = [in_edge[nodes_fwd[(i + 1) % k]].orig.id for i in range(k)]
    return nodes_fwd, channels_fwd


def _level_chosen(nodes: list[str], root: str, in_edge: dict[str, _Edge]) -> list[dict]:
    """本层逐点最低入口的可复算记录。

    cost 取该边在当前收缩层级上的（可能经过修正的）代价 key[0]，而非原始
    通道代价；最深层该值之和加上各环基线代价恰为原始问题总代价。
    """
    return [
        {
            "node": n,
            "channel": in_edge[n].orig.id,
            "cost": in_edge[n].key[0],
        }
        for n in sorted(nodes)
        if n != root
    ]


def _solve_level(
    nodes: list[str],
    root: str,
    edges: list[_Edge],
    depth: int,
    levels: list[dict],
    expansions: list[dict],
    sup_counter: list[int],
) -> list[_Edge] | None:
    """在当前层级上求解；返回以本层 _Edge 表示的入选边，无解返回 None。

    递归下降经过每个收缩层时向 levels 追加一条记录（含环与代价修正明细），
    递归上升展开超点时向 expansions 追加一条替换记录；最深的无环层以
    cycle=None 收尾。levels 按深度 0,1,2,… 排列，expansions 按先内层后外层
    （即收缩顺序的逆序）排列。
    """
    in_edge: dict[str, _Edge] = {}
    for n in sorted(nodes):
        if n == root:
            continue
        best: _Edge | None = None
        for e in edges:
            if e.v == n and (best is None or e.key < best.key):
                best = e
        if best is None:
            return None  # 某点无入边：本层不可解
        in_edge[n] = best

    cycle = _find_cycle(nodes, root, in_edge)
    if cycle is None:
        # 最深层：逐点最低入口不再闭合成环，递归到此触底
        levels.append(
            {
                "depth": depth,
                "nodes": sorted(nodes),
                "chosen": _level_chosen(nodes, root, in_edge),
                "cycle": None,
            }
        )
        return [in_edge[n] for n in sorted(nodes) if n != root]

    # 当前层选出的最低入口闭合成有向环 —— 记录收缩并把环压成超点
    sup_counter[0] += 1
    used = set(nodes) | {e.orig.id for e in edges}
    sname = _fresh_supernode(sup_counter[0], used)
    cyc = set(cycle)
    nodes_fwd, channels_fwd = _cycle_forward(cycle, in_edge)
    cycle_edges = set(channels_fwd)

    rewired_in: list[dict] = []
    dropped_internal: list[str] = []
    new_edges: list[_Edge] = []
    for e in edges:
        u_in, v_in = e.u in cyc, e.v in cyc
        if u_in and v_in:
            if e.orig.id not in cycle_edges:
                dropped_internal.append(e.orig.id)
            continue
        if v_in:
            base = in_edge[e.v].key
            nkey = (e.key[0] - base[0], e.key[1] - base[1], e.key[2])
            new_edges.append(_Edge(e.orig, e.u, sname, nkey, enters=e.v, lower=e))
            rewired_in.append(
                {
                    "channel": e.orig.id,
                    "from": e.u,
                    "to": e.v,
                    "original_cost": e.key[0],
                    "adjusted_cost": nkey[0],
                    "enters": e.v,
                }
            )
        elif u_in:
            new_edges.append(_Edge(e.orig, sname, e.v, e.key, enters=e.v, lower=e))
        else:
            # 未受影响的边也必须包一层，保证每条新层级的边恰有一级 lower
            # 指向本层——否则展开时会越过本层直接解包到外层。
            new_edges.append(_Edge(e.orig, e.u, e.v, e.key, enters=e.v, lower=e))

    levels.append(
        {
            "depth": depth,
            "nodes": sorted(nodes),
            "chosen": _level_chosen(nodes, root, in_edge),
            "cycle": {
                "nodes": nodes_fwd,
                "channels": channels_fwd,
                "supernode": sname,
                # 列表按标识排序，保证与通道录入顺序无关
                "rewired_in": sorted(rewired_in, key=lambda r: r["channel"]),
                "dropped_internal": sorted(dropped_internal),
            },
        }
    )

    new_nodes = [n for n in nodes if n not in cyc] + [sname]
    sub = _solve_level(new_nodes, root, new_edges, depth + 1, levels, expansions, sup_counter)
    if sub is None:
        return None

    entering = [e for e in sub if e.v == sname]
    # 超点非根，下一层解中恰有一条边进入它
    assert len(entering) == 1, "收缩层解中超点入边数量不为 1"
    entering_edge = entering[0]
    removed = in_edge[entering_edge.enters].orig.id
    # 保留环上除被替换边外的全部环边，顺序沿用沿环方向的展示顺序
    kept = [cid for cid in channels_fwd if cid != removed]
    expansions.append(
        {
            "supernode": sname,
            "entering_channel": entering_edge.orig.id,
            "enters_node": entering_edge.enters,
            "removed_cycle_channel": removed,
            "kept_cycle_channels": kept,
        }
    )

    kept_edges = [in_edge[v] for v in cycle if v != entering_edge.enters]
    result: list[_Edge] = []
    for e in sub:
        result.append(e.lower if e.lower is not None else e)
    result.extend(kept_edges)
    return result


def _edmonds(
    nodes: list[str], root: str, edges: list[_Edge]
) -> tuple[list[_Edge], list[dict], list[dict]] | None:
    """完整 Edmonds 运行；返回 (入选边, 层级记录, 展开记录) 或 None。"""
    levels: list[dict] = []
    expansions: list[dict] = []
    picked = _solve_level(list(nodes), root, edges, 0, levels, expansions, [0])
    if picked is None:
        return None
    assert levels and levels[-1]["cycle"] is None, "最深层记录必须无环"
    assert [lv["depth"] for lv in levels] == list(range(len(levels))), "层级深度须连续"
    return picked, levels, expansions


# ---------------------------------------------------------------------------
# 强制入选约束下的最小代价（用于规范树的字典序贪心）
# ---------------------------------------------------------------------------


class _DSU:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        p = self.parent
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _min_cost_with_forced(
    points: list[str], root: str, channels: list[Channel], forced: list[Channel]
) -> int | None:
    """在必须包含 forced 中全部通道的前提下求最小总代价；不可行返回 None。"""
    parent: dict[str, str] = {}
    for f in forced:
        if f.v == root or f.v in parent:
            return None  # 根不能有入边；每点至多一条入边
        parent[f.v] = f.u
    # 强制边内部不得成环（函数图：每点至多一个父指针，沿链走访判环）
    for start in parent:
        seen: set[str] = set()
        cur = start
        while cur in parent:
            if cur in seen:
                return None
            seen.add(cur)
            cur = parent[cur]

    dsu = _DSU(points)
    for f in forced:
        dsu.union(f.u, f.v)

    comp = {p: dsu.find(p) for p in points}
    head: dict[str, str] = {}
    for p in points:
        if p not in parent:  # 每个连通块恰有一个无强制入边的点（头）
            head[comp[p]] = p

    forced_ids = {f.id for f in forced}
    red_edges: list[_Edge] = []
    for c in channels:
        if c.id in forced_ids:
            continue
        cu, cv = comp[c.u], comp[c.v]
        if cu == cv:
            continue  # 块内边：成环或重复入边
        if head[cv] != c.v:
            continue  # 终点已有强制入边
        red_edges.append(_Edge(c, cu, cv, (c.cost, 0, c.id), enters=cv, lower=None))

    nodes = sorted(set(comp.values()))
    root_comp = comp[root]
    sub = _edmonds(nodes, root_comp, red_edges)
    if sub is None:
        return None
    picked = sub[0]
    return sum(f.cost for f in forced) + sum(e.orig.cost for e in picked)


# ---------------------------------------------------------------------------
# 顶层求解
# ---------------------------------------------------------------------------


def reachable_from(root: str, channels: list[Channel]) -> set[str]:
    adj: dict[str, list[str]] = {}
    for c in channels:
        adj.setdefault(c.u, []).append(c.v)
    seen = {root}
    stack = [root]
    while stack:
        u = stack.pop()
        for v in adj.get(u, ()):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def solve(points: list[str], root: str, channels: list[Channel]) -> dict:
    """求解并组装 API 结果。输入须已通过 validate_problem。"""
    reach = reachable_from(root, channels)
    unreachable = sorted(p for p in points if p not in reach)
    if unreachable:
        return {
            "status": "unsolvable",
            "reason": "存在无法自注入根经有向通道到达的采样点，"
            "无法满足“每个非根点恰有一条入选通道并从根可达”。",
            "unreachable": unreachable,
        }

    # 1) 最小总代价
    base_edges = [
        _Edge(c, c.u, c.v, (c.cost, 0, c.id), enters=c.v, lower=None) for c in channels
    ]
    run = _edmonds(list(points), root, base_edges)
    assert run is not None, "全部可达但 Edmonds 无解，内部不一致"
    best_cost = sum(e.orig.cost for e in run[0])

    # 2) 规范树：按标识升序贪心强制入选
    forced: list[Channel] = []
    for c in sorted(channels, key=lambda x: x.id):
        trial_cost = _min_cost_with_forced(points, root, channels, forced + [c])
        if trial_cost == best_cost:
            forced.append(c)
    canonical_ids = sorted(c.id for c in forced)

    # 3) 以 (代价, 非规范边惩罚, 标识) 为键重跑，产出对应规范树的收缩记录
    canon = set(canonical_ids)
    keyed_edges = [
        _Edge(c, c.u, c.v, (c.cost, 0 if c.id in canon else 1, c.id), enters=c.v, lower=None)
        for c in channels
    ]
    final_run = _edmonds(list(points), root, keyed_edges)
    assert final_run is not None
    picked, levels, expansions = final_run
    final_ids = sorted(e.orig.id for e in picked)
    assert final_ids == canonical_ids, "规范树重跑结果与强制集不一致"

    by_id = {c.id: c for c in channels}
    tree = [
        {"id": cid, "from": by_id[cid].u, "to": by_id[cid].v, "cost": by_id[cid].cost}
        for cid in final_ids
    ]
    return {
        "status": "ok",
        "total_cost": best_cost,
        "tree": tree,
        "canonical_ids": final_ids,
        "record": {
            "levels": levels,
            "expansions": expansions,
            "contractions": sum(1 for lv in levels if lv["cycle"]),
        },
    }


# ---------------------------------------------------------------------------
# 记录复算（供测试与 verify 服务核对证据链）
# ---------------------------------------------------------------------------


def replay_record(
    points: list[str], root: str, channels: list[Channel], record: dict
) -> list[str]:
    """根据收缩 / 展开记录**独立**复算最终入选通道标识（升序）。

    不是简单照抄记录给出的边集，而是仅依据原始输入与记录中声明的选择，
    从零重放整条 Edmonds 证据链并逐层核对：

      * 每层每个非根（超）点恰有一条入选边，且其声明代价确实是当前层
        全部候选入口中的最小值（并列时允许任选其一并列边）；
      * 记录的环必须正是逐点最低入口函数图上的有向环（漏报环会被发现），
        环节点 / 环边 / 超点编号一致；
      * 每条入环候选的修正代价 = 原当前代价 − 进入点当前入口代价，
        环内非环边必须完整记入 dropped_internal；
      * 层间代价守恒：下一层入选代价之和 + 本层环基线代价 == 本层之和；
      * 展开先内后外、与超点一一对应：进入通道在当时选中集内，被替换边
        恰为进入点在该层的最低入口，保留边为其余环边；
      * 最终每非根点恰一条入边、无环、自根可达，且逐边原始代价之和满足
        最深层代价 + 各环基线代价的恒等式。
    """
    by_id = {c.id: c for c in channels}
    levels: list[dict] = record.get("levels", [])
    expansions: list[dict] = record.get("expansions", [])
    if not levels:
        raise AssertionError("记录缺少层级信息")
    if [lv["depth"] for lv in levels] != list(range(len(levels))):
        raise AssertionError("层级深度不连续")
    if levels[-1]["cycle"] is not None:
        raise AssertionError("最深层仍含环，记录不完整")

    # 当前层图状态：每条仍存活的原始通道维护当前层尾/头与当前（修正）代价
    cur_tail = {c.id: c.u for c in channels}
    cur_head = {c.id: c.v for c in channels}
    cur_cost = {c.id: c.cost for c in channels}
    active = set(by_id)
    active_nodes = set(points)
    cycles_by_super: dict[str, dict] = {}
    super_depth: dict[str, int] = {}
    total_baseline = 0
    leaf_pick_sum = 0
    chosen_by_level: list[dict[str, str]] = []

    for depth, lv in enumerate(levels):
        if set(lv["nodes"]) != active_nodes:
            raise AssertionError(f"第 {depth} 层节点集合与收缩过程不一致")
        picked: dict[str, str] = {}
        for item in lv["chosen"]:
            node, cid = item["node"], item["channel"]
            if node == root or node not in active_nodes:
                raise AssertionError(f"第 {depth} 层选择记录了非法节点 {node}")
            if node in picked:
                raise AssertionError(f"第 {depth} 层节点 {node} 有重复入选边")
            if cid not in active or cur_head[cid] != node:
                raise AssertionError(f"通道 {cid} 在第 {depth} 层并不进入 {node}")
            if item["cost"] != cur_cost[cid]:
                raise AssertionError(
                    f"通道 {cid} 在第 {depth} 层的声明代价 {item['cost']} "
                    f"与独立重算的当前代价 {cur_cost[cid]} 不一致"
                )
            picked[node] = cid
        if set(picked) != active_nodes - {root}:
            raise AssertionError(f"第 {depth} 层未为每个非根点各选一条入口")

        # 独立地按当前代价检查最低入口（同代价并列允许记录任选其一）
        for node, cid in picked.items():
            for eid in active:
                if cur_head[eid] == node and cur_cost[eid] < cur_cost[cid]:
                    raise AssertionError(
                        f"第 {depth} 层进入 {node} 的 {cid}（代价 {cur_cost[cid]}）"
                        f"不是最低入口：{eid} 代价仅 {cur_cost[eid]}"
                    )

        # 在记录的入选函数图上独立找环
        found = _find_cycle(sorted(active_nodes), root, _MapEdges(picked, cur_tail))
        cyc_rec = lv["cycle"]
        if depth < len(levels) - 1:
            if cyc_rec is None:
                raise AssertionError(f"第 {depth} 层存在有向环但记录漏报收缩")
            if found is None:
                raise AssertionError(f"第 {depth} 层记录了环，但按入选边重算无环")
            nodes_fwd, channels_fwd = _cycle_forward(
                found, _MapEdges(picked, cur_tail)
            )
            if cyc_rec["nodes"] != nodes_fwd or cyc_rec["channels"] != channels_fwd:
                raise AssertionError(f"第 {depth} 层环节点 / 环边与独立重算不一致")
            sname = cyc_rec["supernode"]
            if sname in active_nodes:
                raise AssertionError(f"超点名 {sname} 与现有节点冲突")
            cyc_nodes = set(found)
            baseline = sum(cur_cost[picked[v]] for v in cyc_nodes)
            total_baseline += baseline

            # 独立重算入环候选修正代价与环内丢弃边
            expect_rewired: dict[str, dict] = {}
            expect_dropped: set[str] = set()
            for eid in sorted(active):
                u_in, v_in = cur_tail[eid] in cyc_nodes, cur_head[eid] in cyc_nodes
                if u_in and v_in:
                    if eid not in channels_fwd:
                        expect_dropped.add(eid)
                    continue
                if v_in:
                    head = cur_head[eid]
                    expect_rewired[eid] = {
                        "channel": eid,
                        "from": cur_tail[eid],
                        "to": head,
                        "original_cost": cur_cost[eid],
                        "adjusted_cost": cur_cost[eid] - cur_cost[picked[head]],
                        "enters": head,
                    }
            got_rewired = {r["channel"]: r for r in cyc_rec["rewired_in"]}
            if set(got_rewired) != set(expect_rewired):
                raise AssertionError(f"第 {depth} 层入环候选集合与独立重算不一致")
            for eid, want in expect_rewired.items():
                if got_rewired[eid] != want:
                    raise AssertionError(f"第 {depth} 层候选 {eid} 的修正明细不一致")
            if set(cyc_rec["dropped_internal"]) != expect_dropped:
                raise AssertionError(f"第 {depth} 层环内丢弃边集合与独立重算不一致")

            # 执行收缩，推进到下一层
            new_cost, new_tail, new_head = {}, {}, {}
            for eid in active:
                u_in, v_in = cur_tail[eid] in cyc_nodes, cur_head[eid] in cyc_nodes
                if u_in and v_in:
                    continue
                new_tail[eid] = sname if u_in else cur_tail[eid]
                if v_in:
                    new_head[eid] = sname
                    new_cost[eid] = cur_cost[eid] - cur_cost[picked[cur_head[eid]]]
                else:
                    new_head[eid] = cur_head[eid]
                    new_cost[eid] = cur_cost[eid]
            active = {eid for eid in active
                      if not (cur_tail[eid] in cyc_nodes and cur_head[eid] in cyc_nodes)}
            cur_tail, cur_head, cur_cost = new_tail, new_head, new_cost
            active_nodes = (active_nodes - cyc_nodes) | {sname}
            cycles_by_super[sname] = cyc_rec
            super_depth[sname] = depth
        else:
            if found is not None:
                raise AssertionError("最深层入选边仍闭合成环")
            leaf_pick_sum = sum(cur_cost[picked[n]] for n in picked)
        chosen_by_level.append(picked)

    if record.get("contractions") != len(cycles_by_super):
        raise AssertionError(
            f"contractions={record.get('contractions')} 与层级中的环数 "
            f"{len(cycles_by_super)} 不一致"
        )

    # 展开记录：数量、超点、先后次序（先内后外 = 收缩深度严格递减）
    exp_supers = [e["supernode"] for e in expansions]
    if sorted(exp_supers) != sorted(cycles_by_super):
        raise AssertionError("展开记录与收缩超点不是一一对应")
    if [super_depth[s] for s in exp_supers] != sorted(
        (super_depth[s] for s in exp_supers), reverse=True
    ):
        raise AssertionError("展开次序不是先内后外")

    selected: set[str] = {c["channel"] for c in levels[-1]["chosen"]}
    for exp in expansions:
        sname = exp["supernode"]
        cyc = cycles_by_super[sname]
        depth = super_depth[sname]
        picked = chosen_by_level[depth]
        entering = exp["entering_channel"]
        enters_node = exp["enters_node"]
        if entering not in selected:
            raise AssertionError(
                f"展开 {sname} 的进入通道 {entering} 不在当前选中集"
            )
        # 进入通道必须是本层一条环外→环内的入环候选（rewired_in 已在上面
        # 依独立重放状态逐项核对过），其落点须与 enters_node 一致。嵌套环时
        # 该候选在更深层可能再次被改写，故不要求它就是下一层的 chosen。
        rew = {r["channel"]: r for r in cyc["rewired_in"]}
        if entering not in rew:
            raise AssertionError(f"通道 {entering} 不是超点 {sname} 的入环候选")
        if rew[entering]["enters"] != enters_node:
            raise AssertionError(
                f"展开 {sname} 的进入点 {enters_node} 与候选记录 "
                f"{rew[entering]['enters']} 不一致"
            )
        if enters_node not in cyc["nodes"]:
            raise AssertionError(f"展开 {sname} 的进入点 {enters_node} 不属于该环")
        removed = picked[enters_node]
        if exp["removed_cycle_channel"] != removed:
            raise AssertionError(
                f"展开 {sname} 应替换 {enters_node} 的最低入口 {removed}，"
                f"记录却为 {exp['removed_cycle_channel']}"
            )
        expect_kept = [cid for cid in cyc["channels"] if cid != removed]
        if exp["kept_cycle_channels"] != expect_kept:
            raise AssertionError(f"展开 {sname} 的保留环边序列与独立重算不一致")
        if removed in selected:
            raise AssertionError(f"被替换环边 {removed} 不应仍在选中集")
        selected.update(expect_kept)

    for cid in selected:
        if cid not in by_id:
            raise AssertionError(f"选中通道 {cid} 不在输入中")
    # 结构校验：每非根点恰一条入边、无环、自根可达
    indeg: dict[str, int] = {}
    for cid in selected:
        indeg[by_id[cid].v] = indeg.get(by_id[cid].v, 0) + 1
    for p in points:
        want = 0 if p == root else 1
        if indeg.get(p, 0) != want:
            raise AssertionError(f"点 {p} 的入选入边数为 {indeg.get(p, 0)}，应为 {want}")
    sub_channels = [by_id[cid] for cid in selected]
    if reachable_from(root, sub_channels) != set(points):
        raise AssertionError("复算结果不能自根到达全部点")

    # 代价证据链守恒：最终树原始代价之和 == 最深层修正代价之和 + 各环基线
    final_cost = sum(by_id[cid].cost for cid in selected)
    if final_cost != leaf_pick_sum + total_baseline:
        raise AssertionError(
            f"代价守恒不成立：最终树 {final_cost} != 最深层 {leaf_pick_sum} "
            f"+ 环基线 {total_baseline}"
        )
    return sorted(selected)


class _MapEdges:
    """把 {节点: 通道标识} 与当前尾点表适配为 _find_cycle / _cycle_forward 所需
    的 in_edge 视图（只用到 .u 与 .orig.id）。"""

    def __init__(self, picked: dict[str, str], cur_tail: dict[str, str]):
        self._picked = picked
        self._cur_tail = cur_tail

    def __getitem__(self, node: str) -> "_MapEdge":
        cid = self._picked[node]
        return _MapEdge(self._cur_tail[cid], cid)


class _MapEdge:
    __slots__ = ("u", "orig")

    def __init__(self, u: str, cid: str):
        self.u = u
        self.orig = _MapOrig(cid)


class _MapOrig:
    __slots__ = ("id",)

    def __init__(self, cid: str):
        self.id = cid
