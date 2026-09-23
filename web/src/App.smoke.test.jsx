import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App from "./App.jsx";

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
