import { describe, expect, it } from "vitest";
import { parseChannels, parsePoints, reachableFrom, validateAll } from "./parse";

describe("parsePoints", () => {
  it("解析空白/逗号/分号分隔的标识", () => {
    const { points, errors } = parsePoints("r, a;b  c\n d");
    expect(errors).toEqual([]);
    expect(points).toEqual(["r", "a", "b", "c", "d"]);
  });
  it("拒绝过少采样点", () => {
    const { errors } = parsePoints("r");
    expect(errors.length).toBeGreaterThan(0);
  });
  it("拒绝重复与非 ASCII 标识", () => {
    const { errors } = parsePoints("r a a 点");
    expect(errors.some((e) => e.includes("重复"))).toBe(true);
    expect(errors.some((e) => e.includes("非法"))).toBe(true);
  });
  it("拒绝超过 40 个点", () => {
    const pts = Array.from({ length: 41 }, (_, i) => `p${i}`).join(" ");
    expect(parsePoints(pts).errors.length).toBeGreaterThan(0);
  });
});

describe("parseChannels", () => {
  it("解析四段式行并忽略注释", () => {
    const { channels, errors } = parseChannels("# 注释\ne1, r, a, 5\ne2 a b 0\n");
    expect(errors).toEqual([]);
    expect(channels).toEqual([
      { id: "e1", from: "r", to: "a", cost: 5 },
      { id: "e2", from: "a", to: "b", cost: 0 },
    ]);
  });
  it("拒绝段数不对与负代价", () => {
    const { errors } = parseChannels("e1, r, a\ne2, r, a, -1\n");
    expect(errors.length).toBe(2);
  });
  it("拒绝超过 160 条", () => {
    const text = Array.from({ length: 161 }, (_, i) => `c${i}, r, a, 1`).join("\n");
    expect(parseChannels(text).errors.length).toBeGreaterThan(0);
  });
});

describe("validateAll", () => {
  const pts = ["r", "a", "b"];
  it("通过合法输入（含平行通道）", () => {
    const errs = validateAll(pts, "r", [
      { id: "c1", from: "r", to: "a", cost: 1 },
      { id: "c2", from: "r", to: "a", cost: 2 },
    ]);
    expect(errs).toEqual([]);
  });
  it("拒绝自环 / 未知端点 / 重复标识 / 根不在点集", () => {
    const errs = validateAll(pts, "x", [
      { id: "c1", from: "a", to: "a", cost: 1 },
      { id: "c1", from: "r", to: "zz", cost: 1 },
    ]);
    expect(errs.some((e) => e.includes("自环"))).toBe(true);
    expect(errs.some((e) => e.includes("重复"))).toBe(true);
    expect(errs.some((e) => e.includes("不是已知采样点"))).toBe(true);
    expect(errs.some((e) => e.includes("注入根"))).toBe(true);
  });
});

describe("reachableFrom", () => {
  it("沿有向通道可达", () => {
    const reach = reachableFrom("r", [
      { id: "c1", from: "r", to: "a", cost: 1 },
      { id: "c2", from: "a", to: "b", cost: 1 },
      { id: "c3", from: "z", to: "r", cost: 1 },
    ]);
    expect([...reach].sort()).toEqual(["a", "b", "r"]);
  });
});
