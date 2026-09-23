import { edgePath, NODE_R } from "../lib/layout";

/** SVG 网络图：全部输入通道为底图，规范树高亮，支持收缩记录联动。 */
export default function GraphView({
  points,
  root,
  channels,
  selectedIds,
  layout,
  geom,
  unreachable,
  selectedId,
  highlight,
  onSelect,
}) {
  const { pos, width, height } = layout;
  const treeSet = new Set(selectedIds || []);
  const hl = highlight || { channelIds: new Set(), nodeIds: new Set(), removedIds: new Set(), kind: null };
  const unreach = new Set(unreachable || []);

  return (
    <svg
      className="graph"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="汇流树网络图"
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--edge)" />
        </marker>
        <marker id="arrow-tree" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="8" markerHeight="8" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--tree)" />
        </marker>
        <marker id="arrow-hl" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="8" markerHeight="8" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--hl)" />
        </marker>
      </defs>

      {channels.map((c) => {
        const a = pos[c.from];
        const b = pos[c.to];
        if (!a || !b) return null;
        const p = edgePath(a, b, geom.get(c.id)?.bend ?? 0);
        const inTree = treeSet.has(c.id);
        const inHl = hl.channelIds.has(c.id);
        const isRemoved = hl.removedIds?.has(c.id);
        const isSel = selectedId === c.id;
        let cls = "edge";
        if (inHl) cls += " edge-hl";
        else if (isSel) cls += " edge-sel";
        else if (isRemoved) cls += " edge-removed";
        else if (inTree) cls += " edge-tree";
        else cls += " edge-dim";
        const marker = inHl
          ? "url(#arrow-hl)"
          : inTree
            ? "url(#arrow-tree)"
            : "url(#arrow)";
        return (
          <g key={c.id} className={cls} onClick={() => onSelect(c.id)}>
            <path className="edge-hit" d={p.d} markerEnd={marker} />
            <path className="edge-line" d={p.d} markerEnd={marker} />
            <g transform={`translate(${p.labelX},${p.labelY})`} className="edge-label">
              <rect x="-18" y="-9" width="36" height="16" rx="3" />
              <text textAnchor="middle" dy="3">
                {c.cost}
              </text>
            </g>
          </g>
        );
      })}

      {points.map((p) => {
        const { x, y } = pos[p];
        const isRoot = p === root;
        const isUnreach = unreach.has(p);
        const inHl = hl.nodeIds.has(p);
        const cls = `node ${isRoot ? "node-root" : ""} ${isUnreach ? "node-unreachable" : ""} ${inHl ? "node-hl" : ""}`;
        return (
          <g key={p} className={cls} transform={`translate(${x},${y})`}>
            <circle r={NODE_R} />
            <text textAnchor="middle" dy="4">
              {p}
            </text>
            {isRoot && (
              <text className="root-tag" textAnchor="middle" y={-NODE_R - 8}>注入根</text>
            )}
            {isUnreach && (
              <text className="root-tag bad" textAnchor="middle" y={NODE_R + 16}>不可达</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
