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

    levels / expansions 收集可复算记录。
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
        return [in_edge[n] for n in sorted(nodes) if n != root]

    sup_counter[0] += 1
    used = set(nodes) | {e.orig.id for e in edges}
    sname = _fresh_supernode(sup_counter[0], used)
    cyc = set(cycle)

    new_edges: list[_Edge] = []
    for e in edges:
        u_in, v_in = e.u in cyc, e.v in cyc
        if u_in and v_in:
            continue
        if v_in:
            base = in_edge[e.v].key
            nkey = (e.key[0] - base[0], e.key[1] - base[1], e.key[2])
            new_edges.append(_Edge(e.orig, e.u, sname, nkey, enters=e.v, lower=e))
        elif u_in:
            new_edges.append(_Edge(e.orig, sname, e.v, e.key, enters=e.v, lower=e))
        else:
            # 未受影响的边也必须包一层，保证每条新层级的边恰有一级 lower
            # 指向本层——否则展开时会越过本层直接解包到外层。
            new_edges.append(_Edge(e.orig, e.u, e.v, e.key, enters=e.v, lower=e))

    new_nodes = [n for n in nodes if n not in cyc] + [sname]
    sub = _solve_level(new_nodes, root, new_edges, depth + 1, levels, expansions, sup_counter)
    if sub is None:
        return None

    entering = [e for e in sub if e.v == sname]
    # 超点非根，下一层解中恰有一条边进入它
    assert len(entering) == 1, "收缩层解中超点入边数量不为 1"
    entering_edge = entering[0]
    kept = [in_edge[v] for v in cycle if v != entering_edge.enters]

    result: list[_Edge] = []
    for e in sub:
        result.append(e.lower if e.lower is not None else e)
    result.extend(kept)
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
    chosen = []
    for edge in sorted(picked, key=lambda item: item.orig.v):
        chosen.append(
            {
                "node": edge.orig.v,
                "channel": edge.orig.id,
                "cost": edge.orig.cost,
            }
        )
    levels.append(
        {
            "depth": 0,
            "nodes": sorted(nodes),
            "chosen": chosen,
            "cycle": None,
        }
    )
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
    """根据收缩 / 展开记录复算最终入选通道标识（升序）。

    复算规则：叶子层（无环层）的入选通道 ∪ 每次展开保留的环边。
    同时校验记录内部一致性：每次展开的进入通道须已在当前选中集内、
    被替换的环边须属于对应环、最终每非根点恰有一条入边且自根可达。
    """
    levels: list[dict] = record["levels"]
    expansions: list[dict] = record["expansions"]
    if not levels:
        raise AssertionError("记录缺少层级信息")
    leaf = levels[-1]
    if leaf["cycle"] is not None:
        raise AssertionError("最深层仍含环，记录不完整")
    selected: set[str] = {c["channel"] for c in leaf["chosen"]}

    cycles_by_super: dict[str, dict] = {}
    for lv in levels:
        if lv["cycle"]:
            cyc = lv["cycle"]
            cycles_by_super[cyc["supernode"]] = cyc

    for exp in expansions:
        if exp["supernode"] not in cycles_by_super:
            raise AssertionError(f"展开记录引用了未知超点 {exp['supernode']}")
        cyc = cycles_by_super[exp["supernode"]]
        if exp["entering_channel"] not in selected:
            raise AssertionError(
                f"展开 {exp['supernode']} 的进入通道 {exp['entering_channel']} 不在当前选中集"
            )
        if exp["removed_cycle_channel"] not in cyc["channels"]:
            raise AssertionError(
                f"展开 {exp['supernode']} 移除的 {exp['removed_cycle_channel']} 不属于该环"
            )
        for kept in exp["kept_cycle_channels"]:
            if kept not in cyc["channels"]:
                raise AssertionError(
                    f"展开 {exp['supernode']} 保留的 {kept} 不属于该环"
                )
            selected.add(kept)

    by_id = {c.id: c for c in channels}
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
    return sorted(selected)
