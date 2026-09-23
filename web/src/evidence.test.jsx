import { describe, expect, it } from "vitest";
import { buildEvidence } from "./App.jsx";

/** 后端在双零代价环场景下产出的规范记录（与 POST /api/solve 同构）。 */
const DOUBLE_RECORD = {
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
        nodes: ["a", "b"],
        channels: ["e2", "e1"],
        supernode: "S1",
        rewired_in: [
          { channel: "e5", from: "r", to: "a", original_cost: 2, adjusted_cost: 2, enters: "a" },
        ],
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
        nodes: ["c", "d"],
        channels: ["e4", "e3"],
        supernode: "S2",
        rewired_in: [
          { channel: "e6", from: "r", to: "c", original_cost: 2, adjusted_cost: 2, enters: "c" },
          { channel: "e7", from: "S1", to: "c", original_cost: 1, adjusted_cost: 1, enters: "c" },
        ],
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

describe("buildEvidence 双环证据标注", () => {
  const ev = buildEvidence(DOUBLE_RECORD);
  const texts = (id) => (ev.get(id) || []).map((t) => t.text);

  it("破环通道不再被标成第 0 层最低入口", () => {
    expect(texts("e5")).not.toContain("第 0 层最低入口");
    expect(texts("e7")).not.toContain("第 0 层最低入口");
  });

  it("e5/e7 标注为第 2 层（最深层）最低入口且各自带进入超点标签", () => {
    expect(texts("e5")).toContain("第 2 层最低入口");
    expect(texts("e7")).toContain("第 2 层最低入口");
    expect(texts("e5").some((t) => t.includes("进入 S1"))).toBe(true);
    expect(texts("e7").some((t) => t.includes("进入 S2"))).toBe(true);
  });

  it("保留的环边标注为展开时保留，且不声称自己是最低入口", () => {
    expect(texts("e2")).toEqual(["展开 S1 时保留"]);
    expect(texts("e4")).toEqual(["展开 S2 时保留"]);
  });

  it("被替换的环边没有任何证据标签", () => {
    expect(ev.has("e1")).toBe(false);
    expect(ev.has("e3")).toBe(false);
  });
});

describe("buildEvidence 无环场景", () => {
  it("单层无环记录标为第 0 层最低入口", () => {
    const rec = {
      levels: [
        {
          depth: 0,
          chosen: [
            { node: "a", channel: "t1", cost: 1 },
            { node: "b", channel: "t2", cost: 2 },
          ],
          cycle: null,
        },
      ],
      expansions: [],
    };
    const ev = buildEvidence(rec);
    expect(ev.get("t1")[0].text).toBe("第 0 层最低入口");
    expect(ev.get("t2")[0].text).toBe("第 0 层最低入口");
  });
});
