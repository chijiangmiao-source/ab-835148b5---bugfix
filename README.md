# 冰川洞穴染料示踪 · 全局最小汇流树

逐点选择最低误差入口可能闭合成局部循环；本系统用 **Chu–Liu / Edmonds 最小树形图算法**
在全局范围内求一棵以注入根为源、覆盖全部采样点、总代价精确最小的有向汇流树，
并在同优树中输出规范解。

## 功能

- **精确最小化**：手工实现 Edmonds 算法（`api/app/arborescence.py`），不调用任何现成图优化库；
  含 500 组随机图与暴力枚举对拍的单元测试。
- **字典序规范树**：同优树中按「升序通道标识序列」取字典序最小者
  （按标识升序逐个贪心强制入选，验证强制后最优代价不变）。
- **可复算记录**：
  - 每一收缩层各点的选入通道；
  - 每次有向环收缩（环节点/环边、超点、入边代价 `w − w*(v)` 修正、丢弃的环内边）；
  - 每次展开替换（进入通道、进入点、被替换环边、保留环边）。
  - `replay_record()` 只依据记录即可重算出同一棵树并做结构校验。
- **失败诊断**：输入错误（标识、数量、自环、重复、负代价等）返回逐条原因；
  无解时返回全部**不可达点**与说明。页面在失败后**保留全部输入**。
- **联动页面**：React + SVG 网络图，规范树高亮、逐边代价、树边证据标签；
  点击收缩 / 展开记录即在图上联动高亮环节点、进入通道与被替换环边。
- **容器化**：Web 与 API 各自独立 Dockerfile，Docker Compose 编排，
  宿主端口可经 `WEB_PORT` / `API_PORT` 配置，两个服务均带健康检查；
  `verify` 一次性服务运行测试、前后端构建与真实 API/页面核对后以退出码报告。

## 目录

```
api/                 FastAPI 后端
  app/arborescence.py  Edmonds 求解 + 校验 + 记录复算（无第三方图库）
  app/main.py          /api/health、/api/solve
  tests/               单元测试（含暴力对拍）+ API 测试
  Dockerfile
web/                 React + Vite 前端
  src/lib/             输入解析、确定性布局（纯函数，均带测试）
  src/components/      网络图、记录面板、树表面板、输入面板
  Dockerfile           多阶段构建，nginx 同源反代 /api
verify/              一次性核对服务
  verify.py            真实 API 与页面结果核对 + HTTP/页面冒烟
  run.sh               后端测试 → 前端测试 → 前端构建 → API/页面核对
  Dockerfile
docker-compose.yml
```

## 运行

```bash
# 常驻服务（默认页面 http://localhost:8080 ，API http://localhost:8000 ）
docker compose up --build

# 自定义宿主端口
WEB_PORT=18080 API_PORT=18000 docker compose up --build

# 一次性核对（单元测试、前端测试与构建、真实 API/页面样例核对与冒烟）
docker compose run --build --rm verify
echo $?   # 0 表示全部通过
```

页面与 API 同源：nginx 把 `/api/*` 反代到 `api:8000`，浏览器不跨域。

## 接口

`POST /api/solve`

```json
{
  "points": ["r", "a", "b"],
  "root": "r",
  "channels": [
    {"id": "e1", "from": "r", "to": "a", "cost": 5},
    {"id": "e2", "from": "a", "to": "b", "cost": 1}
  ]
}
```

约束：2–40 个唯一可打印 ASCII 点；根必须属于点集；至多 160 条通道，
标识唯一、代价为非负整数、允许平行通道、禁止自环。

成功响应含 `total_cost`、`tree`（逐边代价）、`canonical_ids` 与
`record.levels` / `record.expansions`；无解返回 `status: "unsolvable"`
与 `unreachable`；输入错误返回 HTTP 422、`status: "invalid"` 与 `errors`。

## 算法要点

1. 每个非根点选字典序最小 `(代价, 标识)` 的入边；若不入环，即为最优树。
2. 出现有向环时收缩为超点，进入环的边代价修正为 `w(e) − w*(enters)`，递归求解。
3. 自叶向上展开：以下层解中进入超点的通道进入环内对应节点，断开该节点原环边，
   保留其余环边——代价变化与收缩修正严格抵消。
4. 嵌套环由递归自然处理；每次收缩与展开都写入记录。
5. 规范解：先求最优代价 C*，再按标识升序逐条试探强制入选，
   仅当强制后最优代价仍为 C* 时接受；最后以 `(代价, 非规范惩罚, 标识)`
   为边键重跑 Edmonds，使产出的收缩记录恰好对应规范树。
