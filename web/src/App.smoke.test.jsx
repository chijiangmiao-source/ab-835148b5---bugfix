import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App, { buildEvidence } from "./App.jsx";

describe("<App /> 初屏", () => {
  it("以默认嵌套环样例渲染输入区、图例与提交按钮而不抛错", () => {
    const html = renderToString(<App />);
    expect(html).toContain("全局最小汇流树");
    expect(html).toContain("注入根");
    expect(html).toContain("提交到真实 API 求解");
    // 默认样例通道在底图中渲染（箭头路径）
    expect(html).toContain("<svg");
    expect(html).toContain("嵌套环");
  });
});

describe("buildEvidence 证据标签", () => {
  // 双零代价环场景的记录形状：第 0/1 层各收缩一环，叶层为第 2 层
  const dualRingRecord = {
    levels: [
      {
        depth: 0,
        nodes: ["a", "b", "c", "d", "r"],
        chosen: [
          { node: "a", channel: "e1", cost: 0 },
          { node: "b", channel: "e2", cost: 0 },
          { node: "c", channel: "e3", cost: 0 },
          { node: "d", channel: "e4", cost: 0 },
        ],
        cycle: {
          supernode: "S1",
          nodes: ["a", "b"],
          channels: ["e2", "e1"],
          rewired_in: [],
          dropped_internal: [],
        },
      },
      {
        depth: 1,
        nodes: ["S1", "c", "d", "r"],
        chosen: [
          { node: "S1", channel: "e5", cost: 2 },
          { node: "c", channel: "e3", cost: 0 },
          { node: "d", channel: "e4", cost: 0 },
        ],
        cycle: {
          supernode: "S2",
          nodes: ["c", "d"],
          channels: ["e4", "e3"],
          rewired_in: [],
          dropped_internal: [],
        },
      },
      {
        depth: 2,
        nodes: ["S1", "S2", "r"],
        chosen: [
          { node: "S1", channel: "e5", cost: 2 },
          { node: "S2", channel: "e7", cost: 1 },
        ],
        cycle: null,
      },
    ],
    expansions: [
      {
        supernode: "S2",
        entering_channel: "e7",
        enters_node: "c",
        removed_cycle_channel: "e3",
        kept_cycle_channels: ["e4"],
      },
      {
        supernode: "S1",
        entering_channel: "e5",
        enters_node: "a",
        removed_cycle_channel: "e1",
        kept_cycle_channels: ["e2"],
      },
    ],
    contractions: 2,
  };

  it("破环通道按叶层实际深度标注，而非第 0 层", () => {
    const m = buildEvidence(dualRingRecord);
    const texts = (id) => (m.get(id) || []).map((t) => t.text);
    // e5 / e7 是第 2 层（叶层）最低入口，且分别是两个超点的进入通道
    expect(texts("e5")).toContain("第 2 层最低入口");
    expect(texts("e5")).toContain("进入 S1（经 a）");
    expect(texts("e7")).toContain("第 2 层最低入口");
    expect(texts("e7")).toContain("进入 S2（经 c）");
    // 任何树边都不得被标成“第 0 层最低入口”
    for (const id of ["e2", "e4", "e5", "e7"]) {
      expect(texts(id)).not.toContain("第 0 层最低入口");
    }
  });

  it("保留环边标注来源超点，被替换环边无证据标签", () => {
    const m = buildEvidence(dualRingRecord);
    const texts = (id) => (m.get(id) || []).map((t) => t.text);
    expect(texts("e2")).toEqual(["展开 S1 时保留"]);
    expect(texts("e4")).toEqual(["展开 S2 时保留"]);
    expect(m.get("e1")).toBeUndefined();
    expect(m.get("e3")).toBeUndefined();
  });

  it("无环记录的树边标为第 0 层最低入口", () => {
    const record = {
      levels: [
        {
          depth: 0,
          nodes: ["a", "r"],
          chosen: [{ node: "a", channel: "c1", cost: 1 }],
          cycle: null,
        },
      ],
      expansions: [],
      contractions: 0,
    };
    const m = buildEvidence(record);
    expect((m.get("c1") || []).map((t) => t.text)).toEqual(["第 0 层最低入口"]);
  });
});
