import { useMemo, useState } from "react";
import GraphView from "./components/GraphView";
import InputPanel from "./components/InputPanel";
import RecordPanel from "./components/RecordPanel";
import TreePanel from "./components/TreePanel";
import { buildEdgeGeometries, layeredLayout } from "./lib/layout";
import { parseChannels, parsePoints, reachableFrom, validateAll } from "./lib/parse";
import { SAMPLES } from "./lib/samples";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

/** 由记录条目生成图上的高亮集合。 */
function highlightOf(item, pointSet) {
  const empty = { channelIds: new Set(), nodeIds: new Set(), removedIds: new Set(), kind: null };
  if (!item) return empty;
  const channelIds = new Set();
  const nodeIds = new Set();
  const removedIds = new Set();
  if (item.kind === "level") {
    for (const c of item.data.chosen) channelIds.add(c.channel);
    return { ...empty, channelIds, kind: "level" };
  }
  if (item.kind === "contraction") {
    const cy = item.data;
    for (const n of cy.nodes) if (pointSet.has(n)) nodeIds.add(n);
    for (const cid of cy.channels) channelIds.add(cid);
    for (const r of cy.rewired_in) {
      channelIds.add(r.channel);
      if (pointSet.has(r.to)) nodeIds.add(r.to);
    }
    return { channelIds, nodeIds, removedIds, kind: "contraction" };
  }
  // expansion
  const e = item.data;
  channelIds.add(e.entering_channel);
  for (const k of e.kept_cycle_channels) channelIds.add(k);
  removedIds.add(e.removed_cycle_channel);
  if (pointSet.has(e.enters_node)) nodeIds.add(e.enters_node);
  return { channelIds, nodeIds, removedIds, kind: "expansion" };
}

/** 为每条最终树边汇总其在记录中的证据标签。 */
export function buildEvidence(record) {
  const m = new Map();
  const add = (id, kind, text) => {
    if (!m.has(id)) m.set(id, []);
    m.get(id).push({ kind, text });
  };
  // 最终树边来自：无环叶层（最深层）的最低入口 + 各次展开保留的环边；
  // 叶层深度随收缩次数变化，不能假定是第 0 层。
  const leaf = record.levels[record.levels.length - 1];
  if (leaf) {
    for (const c of leaf.chosen) add(c.channel, "pick", `第 ${leaf.depth} 层最低入口`);
  }
  for (const e of record.expansions) {
    add(e.entering_channel, "enter", `进入 ${e.supernode}（经 ${e.enters_node}）`);
    for (const k of e.kept_cycle_channels) add(k, "keep", `展开 ${e.supernode} 时保留`);
  }
  return m;
}

export default function App() {
  const [pointsText, setPointsText] = useState(SAMPLES.nested.points);
  const [rootText, setRootText] = useState(SAMPLES.nested.root);
  const [channelsText, setChannelsText] = useState(SAMPLES.nested.channels);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null); // 成功响应
  const [failure, setFailure] = useState(null); // 失败（保留输入）
  const [selectedItem, setSelectedItem] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  const parsed = useMemo(() => {
    const p = parsePoints(pointsText);
    const c = parseChannels(channelsText);
    return { points: p.points, channels: c.channels, parseErrors: [...p.errors, ...c.errors] };
  }, [pointsText, channelsText]);

  const layout = useMemo(
    () => layeredLayout(parsed.points, rootText.trim(), parsed.channels),
    [parsed, rootText]
  );
  const geom = useMemo(() => buildEdgeGeometries(parsed.channels), [parsed.channels]);

  const treeSet = useMemo(
    () => new Set(result?.status === "ok" ? result.canonical_ids : []),
    [result]
  );

  const reach = useMemo(
    () =>
      parsed.points.length
        ? reachableFrom(rootText.trim(), parsed.channels)
        : new Set(),
    [parsed, rootText]
  );

  const evidence = useMemo(
    () => (result?.status === "ok" ? buildEvidence(result.record) : new Map()),
    [result]
  );

  const pointSet = useMemo(() => new Set(parsed.points), [parsed.points]);
  const highlight = useMemo(
    () => highlightOf(selectedItem, pointSet),
    [selectedItem, pointSet]
  );

  async function submit() {
    const clientErrors = [
      ...parsed.parseErrors,
      ...validateAll(parsed.points, rootText.trim(), parsed.channels),
    ];
    if (clientErrors.length) {
      setResult(null);
      setFailure({ kind: "invalid", reason: "输入未通过校验", errors: clientErrors });
      return;
    }
    setLoading(true);
    setFailure(null);
    try {
      const resp = await fetch(`${API_BASE}/api/solve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          points: parsed.points,
          root: rootText.trim(),
          channels: parsed.channels.map((c) => ({ id: c.id, from: c.from, to: c.to, cost: c.cost })),
        }),
      });
      const body = await resp.json();
      if (resp.ok && body.status === "ok") {
        setResult(body);
        setFailure(null);
        setSelectedItem(null);
      } else {
        // 输入错误或无解：不清空任何输入
        setResult(null);
        setFailure(
          body.status === "unsolvable"
            ? { kind: "unsolvable", reason: body.reason, unreachable: body.unreachable }
            : { kind: "invalid", reason: body.reason || "服务端校验失败", errors: body.errors || [] }
        );
      }
    } catch (err) {
      setResult(null);
      setFailure({ kind: "network", reason: `无法连接 API：${String(err)}`, errors: [] });
    } finally {
      setLoading(false);
    }
  }

  function loadSample(s) {
    setPointsText(s.points);
    setRootText(s.root);
    setChannelsText(s.channels);
    setResult(null);
    setFailure(null);
    setSelectedItem(null);
    setSelectedId(null);
  }

  const selectedChannel = parsed.channels.find((c) => c.id === selectedId);
  const localUnreachable = parsed.points.filter((p) => !reach.has(p)).sort();

  return (
    <div className="app">
      <header>
        <h1>冰川洞穴染料示踪 · 全局最小汇流树</h1>
        <p className="subtitle">
          逐点选择最低入口可能闭合成局部循环；系统以 Chu–Liu/Edmonds 全局汇流树
          精确最小化总代价，并给出环收缩与展开替换的可复算记录。
        </p>
      </header>

      <div className="layout">
        <aside className="col-input">
          <InputPanel
            pointsText={pointsText}
            rootText={rootText}
            channelsText={channelsText}
            loading={loading}
            onPoints={setPointsText}
            onRoot={setRootText}
            onChannels={setChannelsText}
            onSubmit={submit}
            onLoadSample={loadSample}
          />
          {failure && (
            <div className={`failure failure-${failure.kind}`} role="alert">
              <h3>{failure.kind === "unsolvable" ? "无解" : "提交失败"}</h3>
              <p>{failure.reason}</p>
              {failure.errors?.length > 0 && (
                <ul>{failure.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
              )}
              {failure.unreachable?.length > 0 && (
                <p>
                  不可达点：
                  {failure.unreachable.map((p) => (
                    <code key={p} className="bad-code">{p}</code>
                  ))}
                </p>
              )}
              <p className="muted">输入已保留，可修正后重新提交。</p>
            </div>
          )}
        </aside>

        <main className="col-main">
          <div className="card graph-card">
            <div className="graph-scroll">
              <GraphView
                points={parsed.points}
                root={rootText.trim()}
                channels={parsed.channels}
                selectedIds={result?.status === "ok" ? result.canonical_ids : []}
                layout={layout}
                geom={geom}
                unreachable={failure?.kind === "unsolvable" ? failure.unreachable : localUnreachable}
                selectedId={selectedId}
                highlight={highlight}
                onSelect={(id) => setSelectedId(id === selectedId ? null : id)}
              />
            </div>
            <div className="legend">
              <span className="lg lg-tree" /> 规范树入选通道
              <span className="lg lg-hl" /> 记录联动高亮
              <span className="lg lg-edge" /> 未入选通道
              <span className="lg lg-node-root" /> 注入根
              <span className="lg lg-node-unreach" /> 不可达点
              {selectedChannel && (
                <span className="edge-detail">
                  选中通道 <code>{selectedChannel.id}</code>：
                  {selectedChannel.from} → {selectedChannel.to}，代价 {selectedChannel.cost}
                  {treeSet.has(selectedChannel.id) ? "（入选规范树）" : "（未入选）"}
                </span>
              )}
            </div>
          </div>

          {result?.status === "ok" && (
            <div className="card">
              <TreePanel
                tree={result.tree}
                totalCost={result.total_cost}
                evidence={evidence}
                selectedId={selectedId}
                onSelect={(id) => setSelectedId(id === selectedId ? null : id)}
              />
            </div>
          )}

          {result?.status === "ok" && (
            <div className="card">
              <RecordPanel
                record={result.record}
                selectedItem={selectedItem}
                onSelect={(it) =>
                  setSelectedItem(
                    selectedItem && it.kind === selectedItem.kind && it.depth === selectedItem.depth
                      ? null
                      : it
                  )
                }
              />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
