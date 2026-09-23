import { SAMPLES } from "../lib/samples";

export default function InputPanel({
  pointsText,
  rootText,
  channelsText,
  loading,
  onPoints,
  onRoot,
  onChannels,
  onSubmit,
  onLoadSample,
}) {
  return (
    <form
      className="input-panel"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <h2>输入</h2>

      <label className="field">
        <span>采样点（2–40 个唯一 ASCII 标识，空格 / 逗号分隔）</span>
        <textarea
          rows={2}
          value={pointsText}
          onChange={(e) => onPoints(e.target.value)}
          spellCheck={false}
        />
      </label>

      <label className="field">
        <span>注入根（必须是上述采样点之一）</span>
        <input value={rootText} onChange={(e) => onRoot(e.target.value)} spellCheck={false} />
      </label>

      <label className="field">
        <span>
          有向通道（至多 160 条，每行「标识, 起点, 终点, 非负整数代价」，# 为注释；
          允许平行通道，禁止自环）
        </span>
        <textarea
          rows={12}
          className="mono"
          value={channelsText}
          onChange={(e) => onChannels(e.target.value)}
          spellCheck={false}
        />
      </label>

      <div className="actions">
        <button type="submit" disabled={loading}>
          {loading ? "求解中…" : "提交到真实 API 求解"}
        </button>
      </div>

      <div className="samples">
        <span className="muted">样例：</span>
        {Object.entries(SAMPLES).map(([key, s]) => (
          <button
            key={key}
            type="button"
            className="sample-btn"
            onClick={() => onLoadSample(s)}
          >
            {s.name}
          </button>
        ))}
      </div>
    </form>
  );
}
