/** 内置样例：嵌套环、平行通道、同优规范树、不可达点。 */

export const SAMPLES = {
  nested: {
    name: "嵌套环收缩",
    points: "r a b c d",
    root: "r",
    channels: `# 嵌套有向环：{a,b} 收缩后再与 c 成环
e1, r, a, 5
e2, a, b, 1
e3, b, a, 1
e4, b, c, 1
e5, c, a, 1
e6, c, d, 1`,
  },
  double: {
    name: "并列双零代价环",
    points: "r a b c d",
    root: "r",
    channels: `# 两个并列零代价环：{a,b} 与 {c,d}，e7（b→c）串联
# e5/e6 是代价 2 的根入口；最优树总代价 3：e5 破第一环、e7 跨入第二环
e1, b, a, 0
e2, a, b, 0
e3, d, c, 0
e4, c, d, 0
e5, r, a, 2
e6, r, c, 2
e7, b, c, 1`,
  },
  parallel: {
    name: "平行通道",
    points: "r x y",
    root: "r",
    channels: `# r->x 两条平行通道，选代价更小者
p1, r, x, 3
p2, r, x, 1
p3, x, y, 2
p4, r, y, 9
p5, y, x, 4`,
  },
  canonical: {
    name: "同优规范树",
    points: "r b c d",
    root: "r",
    channels: `# 四棵同优树（代价均为 3），规范解取升序标识序列字典序最小: k1 k2 k4
k1, r, b, 1
k2, b, c, 1
k3, r, c, 1
k4, c, d, 1
k5, r, d, 1`,
  },
  unreachable: {
    name: "不可达点（无解）",
    points: "r a b z",
    root: "r",
    channels: `# z 无法自根到达，求解将失败并指出不可达点
u1, r, a, 1
u2, a, b, 1
u3, z, a, 1`,
  },
};
