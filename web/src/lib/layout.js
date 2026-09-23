/** 确定性分层布局与边几何计算（纯函数，便于测试）。 */

export const NODE_R = 22;
const LAYER_GAP_Y = 130;
const COL_GAP_X = 120;
const MARGIN = 90;

/** 自根按无向 BFS 分层；不可达点置于最底层之下。 */
export function layeredLayout(points, root, channels) {
  const adj = new Map();
  for (const p of points) adj.set(p, []);
  for (const c of channels) {
    if (adj.has(c.from) && adj.has(c.to)) {
      adj.get(c.from).push(c.to);
      adj.get(c.to).push(c.from);
    }
  }
  const depth = new Map();
  if (adj.has(root)) {
    depth.set(root, 0);
    const queue = [root];
    while (queue.length) {
      const u = queue.shift();
      for (const v of adj.get(u)) {
        if (!depth.has(v)) {
          depth.set(v, depth.get(u) + 1);
          queue.push(v);
        }
      }
    }
  }
  let maxDepth = 0;
  for (const d of depth.values()) maxDepth = Math.max(maxDepth, d);
  const restDepth = maxDepth + 1;

  const layers = new Map();
  for (const p of [...points].sort()) {
    const d = depth.has(p) ? depth.get(p) : restDepth;
    if (!layers.has(d)) layers.set(d, []);
    layers.get(d).push(p);
  }

  const pos = {};
  let maxCols = 1;
  for (const [d, layer] of layers) {
    maxCols = Math.max(maxCols, layer.length);
    layer.forEach((p, i) => {
      pos[p] = { x: MARGIN + i * COL_GAP_X, y: MARGIN + d * LAYER_GAP_Y, depth: d };
    });
  }
  // 每层水平居中
  for (const layer of layers.values()) {
    const offset = ((maxCols - layer.length) * COL_GAP_X) / 2;
    for (const p of layer) pos[p].x += offset;
  }
  const width = MARGIN * 2 + (maxCols - 1) * COL_GAP_X;
  const height = MARGIN * 2 + restDepth * LAYER_GAP_Y;
  return { pos, width, height, depthOf: (p) => (depth.has(p) ? depth.get(p) : restDepth) };
}

/** 为每条通道分配弯曲参数：平行通道彼此错开，反向通道让出直线。 */
export function buildEdgeGeometries(channels) {
  const groups = new Map();
  for (const c of channels) {
    const key = `${c.from}→${c.to}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const pairHasReverse = new Map();
  for (const c of channels) {
    pairHasReverse.set(
      `${c.from}→${c.to}`,
      channels.some((o) => o.from === c.to && o.to === c.from)
    );
  }
  const geom = new Map();
  for (const [key, group] of groups) {
    const k = group.length;
    const rev = pairHasReverse.get(key);
    group.forEach((c, i) => {
      let bend = (i - (k - 1) / 2) * 48;
      if (rev) bend += 26;
      geom.set(c.id, { bend });
    });
  }
  return geom;
}

/** 二次贝塞尔路径，端点收缩到节点圆外。 */
export function edgePath(a, b, bend, r = NODE_R) {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const cx = mx + nx * bend;
  const cy = my + ny * bend;
  const trim = (px, py, qx, qy) => {
    const ddx = qx - px;
    const ddy = qy - py;
    const l = Math.hypot(ddx, ddy) || 1;
    return [px + (ddx / l) * r, py + (ddy / l) * r];
  };
  const [sx, sy] = trim(a.x, a.y, cx, cy);
  const [ex, ey] = trim(b.x, b.y, cx, cy);
  return {
    d: `M ${sx} ${sy} Q ${cx} ${cy} ${ex} ${ey}`,
    labelX: (sx + 2 * cx + ex) / 4,
    labelY: (sy + 2 * cy + ey) / 4,
  };
}
