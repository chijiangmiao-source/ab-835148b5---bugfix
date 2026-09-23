/** 收缩 / 展开记录的联动面板。
 *
 * 记录条目：
 *   - level 选择记录：高亮该层选中的全部通道
 *   - contraction 环收缩：高亮环节点与环边，并列出代价修正明细
 *   - expansion 展开替换：高亮进入通道与保留环边，标出被替换的环边
 */
export default function RecordPanel({ record, selectedItem, onSelect }) {
  if (!record) return null;
  const { levels, expansions } = record;

  const items = [];
  levels.forEach((lv) => {
    items.push({ kind: "level", depth: lv.depth, data: lv });
    if (lv.cycle) items.push({ kind: "contraction", depth: lv.depth, data: lv.cycle });
  });
  expansions.forEach((e, i) => {
    items.push({ kind: "expansion", depth: -(i + 1), data: e });
  });

  const keyOf = (it) => `${it.kind}:${it.depth}`;

  return (
    <div className="record-panel">
      <h3>可复算记录（收缩 → 展开）</h3>
      <ol className="record-list">
        {items.map((it) => {
          const active = selectedItem && keyOf(selectedItem) === keyOf(it);
          if (it.kind === "level") {
            const lv = it.data;
            return (
              <li
                key={keyOf(it)}
                className={`record-item ${active ? "active" : ""}`}
                onClick={() => onSelect(it)}
              >
                <span className="rec-tag tag-level">第 {lv.depth} 层 · 选入通道</span>
                <span className="rec-desc">
                  为 {lv.chosen.length} 个非根点各选最低入口：
                  <code>{lv.chosen.map((c) => c.channel).join(", ")}</code>
                </span>
              </li>
            );
          }
          if (it.kind === "contraction") {
            const cy = it.data;
            return (
              <li
                key={keyOf(it)}
                className={`record-item ${active ? "active" : ""}`}
                onClick={() => onSelect(it)}
              >
                <span className="rec-tag tag-contract">环收缩 → {cy.supernode}</span>
                <span className="rec-desc">
                  有向环节点 <code>{cy.nodes.join(" → ")} → {cy.nodes[0]}</code>
                  ；环边 <code>{cy.channels.join(" → ")}</code>
                </span>
                <ul className="rewire-list">
                  {cy.rewired_in.map((r) => (
                    <li key={r.channel}>
                      进入候选 <code>{r.channel}</code>（{r.from}→{r.to}）
                      代价 {r.original_cost} − {r.original_cost - r.adjusted_cost}
                      （{r.enters} 的当前入口）= 修正代价 <strong>{r.adjusted_cost}</strong>
                    </li>
                  ))}
                  {cy.dropped_internal.length > 0 && (
                    <li className="muted">
                      丢弃环内非环边：<code>{cy.dropped_internal.join(", ") || "无"}</code>
                    </li>
                  )}
                </ul>
              </li>
            );
          }
          const e = it.data;
          return (
            <li
              key={keyOf(it)}
              className={`record-item ${active ? "active" : ""}`}
              onClick={() => onSelect(it)}
            >
              <span className="rec-tag tag-expand">展开 {e.supernode} · 替换</span>
              <span className="rec-desc">
                展开通道 <code>{e.entering_channel}</code> 进入点
                <code>{e.enters_node}</code>，替换掉环边
                <code className="bad">{e.removed_cycle_channel}</code>
                ，保留环边 <code>{e.kept_cycle_channels.join(", ")}</code>
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
