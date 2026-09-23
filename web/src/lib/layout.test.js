import { describe, expect, it } from "vitest";
import { buildEdgeGeometries, edgePath, layeredLayout } from "./layout";

const channels = [
  { id: "e1", from: "r", to: "a", cost: 1 },
  { id: "e2", from: "a", to: "b", cost: 1 },
  { id: "e3", from: "b", to: "a", cost: 1 },
  { id: "e4", from: "r", to: "b", cost: 9 },
  { id: "e5", from: "r", to: "b", cost: 9 },
];

describe("layeredLayout", () => {
  it("为每个点给出确定性位置且根在第 0 层", () => {
    const pts = ["r", "a", "b", "z"];
    const l1 = layeredLayout(pts, "r", channels);
    const l2 = layeredLayout(pts, "r", channels);
    expect({ pos: l1.pos, width: l1.width, height: l1.height }).toEqual({
      pos: l2.pos,
      width: l2.width,
      height: l2.height,
    });
    for (const p of pts) expect(l1.pos[p]).toBeDefined();
    expect(l1.pos.r.depth).toBe(0);
    expect(l1.pos.a.depth).toBe(1);
    // 不可达点 z 置于可达层之下
    expect(l1.pos.z.depth).toBeGreaterThan(l1.pos.b.depth);
  });
});

describe("buildEdgeGeometries", () => {
  it("平行通道获得不同弯曲，反向通道让出直线", () => {
    const geom = buildEdgeGeometries(channels);
    expect(geom.get("e4").bend).not.toBe(geom.get("e5").bend);
    expect(geom.get("e1").bend).toBe(0); // 无平行无反向：直线
    expect(geom.get("e2").bend).not.toBe(0); // 与 e3 互为反向
  });
});

describe("edgePath", () => {
  it("生成二次贝塞尔路径且标签点在路径附近", () => {
    const p = edgePath({ x: 0, y: 0 }, { x: 100, y: 0 }, 0, 10);
    expect(p.d.startsWith("M ")).toBe(true);
    expect(p.labelY).toBeCloseTo(0, 5);
    const q = edgePath({ x: 0, y: 0 }, { x: 100, y: 0 }, 40, 10);
    expect(q.labelY).toBeGreaterThan(0);
  });
});
