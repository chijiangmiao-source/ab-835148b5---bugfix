/** 输入解析与客户端校验（与服务端规则保持一致）。 */

export const LIMITS = { minPoints: 2, maxPoints: 40, maxChannels: 160, maxIdLen: 32 };

const ID_RE = /^[!-~]{1,32}$/;

export function isAsciiId(s) {
  return typeof s === "string" && ID_RE.test(s);
}

/** 解析采样点：按空白 / 逗号 / 分号分隔。返回 { points, errors }。 */
export function parsePoints(text) {
  const errors = [];
  const points = text
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  if (points.length < LIMITS.minPoints || points.length > LIMITS.maxPoints) {
    errors.push(
      `采样点数量须为 ${LIMITS.minPoints}..${LIMITS.maxPoints}，当前为 ${points.length}`
    );
  }
  const seen = new Set();
  for (const p of points) {
    if (!isAsciiId(p)) errors.push(`采样点标识非法（1..${LIMITS.maxIdLen} 个可打印 ASCII）: ${p}`);
    else if (seen.has(p)) errors.push(`采样点标识重复: ${p}`);
    seen.add(p);
  }
  return { points, errors };
}

/** 解析通道：每行一条 "id, from, to, cost"（分隔符可为逗号或空白），# 开头为注释。 */
export function parseChannels(text) {
  const errors = [];
  const channels = [];
  const lines = text.split(/\r?\n/);
  lines.forEach((raw, idx) => {
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;
    const parts = line.split(/[\s,]+/).filter((s) => s.length > 0);
    if (parts.length !== 4) {
      errors.push(`第 ${idx + 1} 行：须为 "标识, 起点, 终点, 代价" 四段，实际 ${parts.length} 段`);
      return;
    }
    const [id, from, to, costRaw] = parts;
    if (!/^\d+$/.test(costRaw)) {
      errors.push(`第 ${idx + 1} 行：代价须为非负整数，实际为 "${costRaw}"`);
      return;
    }
    channels.push({ id, from, to, cost: parseInt(costRaw, 10) });
  });
  if (channels.length > LIMITS.maxChannels) {
    errors.push(`通道数量至多为 ${LIMITS.maxChannels}，当前为 ${channels.length}`);
  }
  return { channels, errors };
}

/** 整体校验：返回错误列表（空数组表示可提交）。 */
export function validateAll(points, root, channels) {
  const errors = [];
  const pointSet = new Set(points);
  if (!isAsciiId(root)) errors.push(`注入根标识非法: ${root}`);
  else if (!pointSet.has(root)) errors.push(`注入根 ${root} 不在采样点集合中`);
  const ids = new Set();
  for (const c of channels) {
    if (!isAsciiId(c.id)) errors.push(`通道标识非法: ${c.id}`);
    else if (ids.has(c.id)) errors.push(`通道标识重复: ${c.id}`);
    ids.add(c.id);
    if (!pointSet.has(c.from)) errors.push(`通道 ${c.id} 的起点 ${c.from} 不是已知采样点`);
    if (!pointSet.has(c.to)) errors.push(`通道 ${c.id} 的终点 ${c.to} 不是已知采样点`);
    if (c.from === c.to) errors.push(`通道 ${c.id} 是自环（${c.from} -> ${c.to}），不被允许`);
  }
  return errors;
}

/** 由通道计算自根可达集合（用于在图上标出不可达点）。 */
export function reachableFrom(root, channels) {
  const adj = new Map();
  for (const c of channels) {
    if (!adj.has(c.from)) adj.set(c.from, []);
    adj.get(c.from).push(c.to);
  }
  const seen = new Set([root]);
  const stack = [root];
  while (stack.length) {
    const u = stack.pop();
    for (const v of adj.get(u) || []) {
      if (!seen.has(v)) {
        seen.add(v);
        stack.push(v);
      }
    }
  }
  return seen;
}
