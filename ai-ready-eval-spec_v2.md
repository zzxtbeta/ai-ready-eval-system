# AI-Ready Eval — 工程化 Spec v2

> AI 就绪度评估系统：API + Skill 统一质量框架
>
> 面向开源 · 全中文界面 · 可量化 · 可演示

---

## 一、上一版复盘：必须修复的问题清单

基于对 https://ai-ready-eval-system-g1rh.vercel.app 全站审查，以及 spec v1 的缺陷：

### 界面问题

| 编号 | 问题 | 严重度 |
|------|------|--------|
| UI-1 | 中英文混杂——维度名、按钮、检查项描述大量英文 | 高 |
| UI-2 | 视觉粗糙——白底灰框的 AI slop 默认风格，无品牌感 | 高 |
| UI-3 | Demo 数据与真实评估混在一起——概览/详情/趋势全是硬编码 mock | 高 |
| UI-4 | 上传 spec 后没有结果反馈——/run-eval 声称秒级分析但链路断了 | 高 |
| UI-5 | 趋势数据太假——8 次全部稳步上升无波动 | 中 |
| UI-6 | GitHub 链接未替换——指向 your-org 占位符 | 低 |

### 评估逻辑问题

| 编号 | 问题 | 严重度 |
|------|------|--------|
| EV-1 | 只有静态分析但未标注检测层次 | 高 |
| EV-2 | 权重未公开——75% 综合分看似等权但未说明 | 高 |
| EV-3 | 阈值无依据——70% 为什么是 70%？ | 中 |
| EV-4 | Skill 触发测试只有 10 条，反例太简单 | 中 |
| EV-5 | 缺少 Spec-实现一致性检测（75% API 有 drift） | 中 |
| EV-6 | 缺少 Skill-API 联合检查 | 中 |
| EV-7 | 描述质量只查 todo/fixme，没查"等于没写"的描述 | 中 |
| EV-8 | 缺少 MCP 工具粒度和描述质量检测 | 低 |

### Spec 本身的问题

| 编号 | 问题 |
|------|------|
| SP-1 | Claude Code 指令不够具体——"创建目录结构"太笼统 |
| SP-2 | 无 UI 设计规范——导致生成了丑界面 |
| SP-3 | 未定义数据流——上传→解析→评分→展示的链路不清晰 |
| SP-4 | 无配置文件模板 |
| SP-5 | JSON API 输出格式太简陋 |
| SP-6 | 维度定义重复写在 spec 和代码注释中，应有单一来源 |

---

## 二、产品定位

**AI-Ready Eval** 是开源的 AI 就绪度评估工具。

**核心场景**（按优先级）：
1. **在线快速评估**——上传 OpenAPI spec，30 秒内拿到评分和改进建议
2. **本地深度评估**——CLI 运行，含动态探测和 Agent 试用
3. **持续集成**——CI/CD 中运行，设质量门禁
4. **客户交流**——导出可视化报告用于演示

---

## 三、设计原则（6 条硬性约束）

| 约束 | 说明 |
|------|------|
| **全中文** | 所有界面文字、维度名、检查项、按钮、报告——全中文。代码变量名可英文 |
| **深色主题** | 主背景 #0a0a0f，卡片 #141420，文字 #e2e8f0。参考 Grafana/Linear 的专业工具感 |
| **无假数据** | 概览页无评估历史时显示空状态引导，不显示硬编码 mock |
| **上传即出结果** | /run-eval 上传后同页面渲染结果，纯前端运行，不上传用户数据到服务器 |
| **权重透明** | 综合评分旁可展开查看权重详情和计算公式 |
| **检测层次标注** | 每个维度评分旁标注 `[静态分析]` / `[动态探测]` / `[完整评估]` |

---

## 四、整体架构

### 4.1 目录结构

```
ai-ready-eval/
├── README.md                           # 全中文项目说明
├── LICENSE                             # MIT
├── config.yaml                         # 配置模板
├── requirements.txt
├── cli.py                              # 命令行入口
│
├── api_eval/                           # API 就绪度评估
│   ├── __init__.py
│   ├── scanner.py                      # 静态扫描器
│   ├── prober.py                       # 动态探测器
│   ├── agent_trial.py                  # Agent 试用器
│   ├── scorer.py                       # 评分引擎
│   ├── dimensions/                     # 8 个维度
│   │   ├── __init__.py
│   │   ├── d1_semantic.py              # 语义描述完整性
│   │   ├── d2_response.py              # 响应体量控制
│   │   ├── d3_error.py                 # 错误语义质量
│   │   ├── d4_discovery.py             # 可发现性
│   │   ├── d5_workflow.py              # 工作流文档化
│   │   ├── d6_consistency.py           # 设计一致性
│   │   ├── d7_traffic.py               # 流量韧性
│   │   └── d8_security.py              # 安全就绪度
│   └── report.py
│
├── skill_eval/                         # Skill 质量评估
│   ├── __init__.py
│   ├── structure_check.py              # 结构合规
│   ├── content_analysis.py             # 指令质量
│   ├── trigger_eval.py                 # 触发准确率
│   ├── functional_eval.py              # 功能可靠性
│   ├── integration_eval.py             # 集成协同
│   ├── scorer.py
│   └── report.py
│
├── web/                                # 仪表盘
│   ├── app.py                          # Flask 主应用
│   ├── routes/
│   │   ├── pages.py                    # 页面路由
│   │   └── api.py                      # JSON API
│   ├── services/
│   │   └── report_store.py             # 评估结果存储
│   ├── templates/
│   │   ├── base.html                   # 基础布局
│   │   ├── index.html                  # 概览页
│   │   ├── api_eval.html               # API 详情页
│   │   ├── skill_eval.html             # Skill 详情页
│   │   ├── run_eval.html               # 在线评估页
│   │   ├── trends.html                 # 趋势页
│   │   └── components/
│   │       ├── dimension_card.html
│   │       ├── check_item.html
│   │       └── score_badge.html
│   └── static/
│       ├── css/main.css
│       └── js/
│           ├── eval_runner.js          # 纯前端评估引擎
│           ├── charts.js
│           └── upload.js
│
├── examples/
│   ├── sample_openapi.yaml             # 故意含常见问题的示例
│   └── sample_skill/
│       ├── SKILL.md
│       └── references/
│
├── reports/                            # 评估结果存档
└── docs/
    ├── 维度参考手册.md
    ├── 评分方法论.md
    ├── 部署指南.md
    └── 贡献指南.md
```

### 4.2 配置文件

```yaml
# config.yaml — AI-Ready Eval 配置

语言: zh-CN
报告目录: ./reports

api评估:
  spec文件: ./your_openapi.yaml
  基础地址: ""                          # 动态探测用，静态分析不需要
  认证:
    类型: api_key                        # api_key / bearer / oauth2
    值: ${API_KEY}

  # 维度权重（0-10，0=跳过）
  # 默认权重依据：对 agent 调用成功率的影响程度
  权重:
    语义描述完整性: 10                    # 描述缺失=调错端点/参数
    响应体量控制: 8                       # 上下文爆炸=后续推理全废
    错误语义质量: 8                       # 错误不可读=无法自愈
    可发现性: 7                          # 找不到=根本不会被调用
    设计一致性: 6                         # 不一致=模式外推失败
    安全就绪度: 6                         # 权限过大=安全风险
    流量韧性: 5                          # 限流=任务中断但可恢复
    工作流文档化: 4                       # 缺失=多步任务效率低

  # 检查项阈值（可自定义覆盖默认值）
  阈值:
    端点描述覆盖率: { 通过: 0.90, 部分: 0.70 }
    参数描述覆盖率: { 通过: 0.85, 部分: 0.60 }
    参数示例覆盖率: { 通过: 0.60, 部分: 0.30 }
    默认响应体积上限: 4096               # 字节

  动态探测:
    启用: false
    突发QPS: 10
    突发时长: 3
    超时: 10

  agent试用:
    启用: false
    模型: claude-sonnet-4-20250514
    任务:
      - "查询所有进行中的任务并按优先级排序"
      - "创建新任务并分配给指定用户"

skill评估:
  skill文件: ./your_skill/SKILL.md
  references目录: ./your_skill/references/
  evals文件: ./your_skill/evals.json
  触发evals文件: ./your_skill/trigger_evals.json

  权重:
    结构合规: 7
    指令质量: 8
    触发准确率: 9
    功能可靠性: 10
    集成协同: 5
```

### 4.3 在线评估数据流

```
用户访问 /run-eval
    │
    ├→ 上传 .yaml/.json 文件  ─┐
    │                          ├→ 前端 JS 读取内容
    └→ 粘贴 spec 到文本框    ─┘
                │
                ▼
      eval_runner.js（纯前端）
                │
                ├→ js-yaml 解析为对象
                ├→ 验证基本结构（有 openapi/paths 字段）
                ├→ 逐维度运行 8 项静态检查
                ├→ 按配置权重计算综合评分
                │
                ▼
      同页面渲染结果（上传区收起，结果区展开）
                │
                ├→ 顶部：综合评分卡 + 雷达图
                ├→ 中部：8 个维度卡片（展开/收起）
                ├→ 底部：高优先级修复建议 + 导出按钮
                │
                ▼
      可选：导出 JSON / HTML 报告
```

---

## 五、UI 设计规范

### 5.1 设计方向

参考 Grafana / Linear / Vercel Dashboard。专业数据工具感，不要通用 AI 模板。

### 5.2 色彩

```css
:root {
  /* 基础 */
  --bg-primary: #0a0a0f;
  --bg-card: #141420;
  --bg-card-hover: #1a1a2e;
  --border: #2a2a3e;
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;

  /* 品牌 */
  --accent: #6366f1;
  --accent-hover: #818cf8;

  /* 状态 */
  --pass: #22c55e;
  --partial: #f59e0b;
  --fail: #ef4444;

  /* 等级 */
  --grade-a: #22c55e;
  --grade-b: #6366f1;
  --grade-c: #f59e0b;
  --grade-d: #ef4444;
}
```

### 5.3 字体

```css
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap');

:root {
  --font-sans: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", monospace;
}
```

### 5.4 评分等级视觉

| 等级 | 中文名 | 背景色 | 文字色 |
|------|--------|--------|--------|
| A | 就绪 | var(--grade-a) | 白 |
| B | 可用 | var(--grade-b) | 白 |
| C | 脆弱 | var(--grade-c) | 深色 |
| D | 不可用 | var(--grade-d) | 白 |

### 5.5 导航栏

左侧固定，宽 220px，深色背景。

```
AI-Ready Eval
─────────────
仪表盘
  概览
评估模块
  API 评估详情
  Skill 评估详情
  趋势分析
工具
  ★ 在线评估          ← 主入口高亮
  JSON API
─────────────
GitHub 源码
```

### 5.6 维度卡片组件

```
┌─────────────────────────────────────────────────────────┐
│ 语义描述完整性                      72%  B·可用 [静态]  │
│ 端点/参数/响应字段的描述覆盖率与质量                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ✅ 端点描述覆盖率    16/18 端点有描述 (88.9%)            │
│ ⚠️ 参数描述覆盖率    34/52 参数有描述 (65.4%)           │
│ ❌ 参数示例覆盖率    仅 12/52 参数有示例 (23.1%)         │
│ ⚠️ 响应字段描述率    58% 字段有描述                      │
│ ✅ 描述语言质量      未检测到占位文字                     │
│                                                         │
│ ▸ 发现的问题 (2 项)                                     │
│ ▸ 修复建议 (3 项，按优先级排序)                          │
│ ▸ 阈值说明 (通过≥90% · 部分≥70% · 来源: APIContext)    │
└─────────────────────────────────────────────────────────┘
```

---

## 六、评估维度完整定义

> 完整 8+5 维度定义见 spec v1 第五、六节（本文不再重复）。
> 以下仅列出 v2 新增/修改的内容。

### v2 新增检查项

**维度 1 语义描述 — 新增两项**：

| 检查项 | 权重 | 判定标准 |
|--------|------|---------|
| "等于没写"检测 | 高 | 排除：描述=字段名重复、纯类型声明、< 5 词 |
| 跨字段语义冲突 | 中 | 同概念不同命名（user_id vs userId），同名不同义 |

**维度 4 可发现性 — 新增 Spec-实现一致性**（仅动态探测时）：

| 检查项 | 权重 | 检测层次 |
|--------|------|---------|
| 端点存在性 | 高 | 动态 |
| 响应 schema 匹配 | 高 | 动态 |
| 必填参数验证 | 中 | 动态 |
| 枚举值验证 | 中 | 动态 |

**维度 4 可发现性 — 新增 MCP 工具质量**：

| 检查项 | 权重 | 判定标准 |
|--------|------|---------|
| MCP 工具描述质量 | 中 | 每个 tool 的 description 足够 agent 理解用途 |
| MCP 工具粒度 | 中 | 工具是业务级而非原始 CRUD |

**新模块：Skill-API 联合检查**（同时提供两者时）：

| 检查项 | 权重 | 说明 |
|--------|------|------|
| API 依赖可达性 | 高 | Skill 引用的端点在 spec 中存在 |
| API 就绪度匹配 | 高 | 依赖的 API ≥ B 级 |
| 参数映射正确性 | 中 | Skill 描述的参数名与 spec 一致 |

---

## 七、评分方法论

### 计算公式

```
检查项分：通过=1.0 / 部分=0.5 / 不通过=0.0
检查项权重值：高=3 / 中=2 / 低=1

维度分 = Σ(检查项分 × 检查项权重值) / Σ(检查项权重值)

综合分 = Σ(维度分 × 维度配置权重) / Σ(维度配置权重)
       （只计算实际执行了的维度）
```

### 等级映射

| 综合分 | 等级 | 中文 | 含义 |
|--------|------|------|------|
| ≥ 0.85 | A | 就绪 | 可直接供 agent 使用 |
| ≥ 0.70 | B | 可用 | 基本可用，部分场景需兜底 |
| ≥ 0.50 | C | 脆弱 | 勉强可用，高失败率 |
| < 0.50 | D | 不可用 | 不建议供 agent 使用 |

### 检测层次标注

| 标注 | 含义 |
|------|------|
| `[静态分析]` | 基于 spec 文件文本分析，未验证实际 API 行为 |
| `[静态+动态]` | 分析了 spec，也实际调用了 API |
| `[完整评估]` | 含 agent 端到端任务执行 |

---

## 八、JSON API 输出格式

### GET /api/scores

```json
{
  "评估时间": "2026-03-11T14:30:00+08:00",
  "评估目标": "我的API v2.1",
  "api": {
    "综合分": 0.748,
    "等级": "B",
    "等级名": "可用",
    "检测层次": "静态分析",
    "维度": {
      "语义描述完整性": {
        "分数": 0.72, "等级": "B", "权重": 10,
        "检测层次": "静态",
        "检查项数": 5, "通过": 2, "部分": 2, "不通过": 1
      }
    }
  },
  "skill": null,
  "问题总数": 18,
  "高优先级修复": [
    "为缺失描述的参数添加 description + example",
    "添加字段选择器减少响应体积"
  ]
}
```

---

## 九、给 Claude Code 的执行指令

```
# 任务：构建 AI-Ready Eval v2

严格按本 spec 实现。以下为硬性约束，违反任何一条视为未完成：

1. 全中文界面——所有文字中文
2. 深色主题——#0a0a0f 背景，#141420 卡片，参考 Grafana
3. 上传即出结果——/run-eval 纯前端解析+评估，同页面渲染
4. 无假数据——概览页无评估历史时显示空状态引导
5. 权重可见——综合评分旁可展开查看权重和计算公式
6. 检测层次标注——每个维度旁标 [静态分析] 等
7. 阈值有来源——每个阈值可展开查看依据
8. Noto Sans SC 中文字体

## 阶段 1：核心评估引擎 + 示例文件

创建完整目录结构。
实现 api_eval/scanner.py（8 维度静态检查，含 v2 新增项）。
实现 api_eval/scorer.py（加权评分）。
实现 skill_eval/structure_check.py + content_analysis.py。
创建 examples/sample_openapi.yaml（故意含常见问题，评分约 60-70%）。
创建 examples/sample_skill/SKILL.md（故意含常见问题）。
创建 config.yaml 模板。

验收：python cli.py eval-api --spec examples/sample_openapi.yaml 
输出完整 JSON 评估结果，含 8 维度和每个检查项明细。

## 阶段 2：在线评估页（最关键页面）

创建 Flask 应用 + base.html（深色主题、左侧导航、中文字体）。
创建 run_eval.html + eval_runner.js（纯前端评估）。
实现：上传 spec → 同页面渲染 8 维度结果 → 可展开每个维度。
维度卡片严格按 spec 5.6 节的格式。

验收：浏览器打开 → 上传 sample_openapi.yaml → 看到完整结果。

## 阶段 3：其余页面

概览页：无历史=空状态引导；有历史=最近结果。
API 详情页 + Skill 详情页 + 趋势页。
JSON API（/api/scores）按 spec 第八节格式。

## 阶段 4：报告导出 + CLI

JSON + HTML 导出（HTML 为独立单文件，内嵌 CSS，深色主题）。
cli.py 实现 eval-api / eval-skill / eval-all / serve 命令。

## 阶段 5：文档 + 开源

README.md + docs/ 下 4 文档（全中文）。
LICENSE (MIT) + .gitignore + requirements.txt。

每阶段完成后向我确认再进下一阶段。
```

---

## 十、参考来源

| 来源 | 影响范围 |
|------|----------|
| The New Stack —"How To Prepare Your API for AI Agents" | 全部 8 个 API 维度 |
| The New Stack —"Why Most APIs Fail in AI Systems" | 语义描述、一致性检测 |
| Nordic APIs —"10 AI-Driven API Economy Predictions for 2026" | 安全（JIT auth）、MCP |
| Nordic APIs —"Comparing 7 AI Agent-to-API Standards" | 可发现性 |
| Anthropic — skill-creator 工程规范 | Skill 全部 5 维度 |
| OpenAI —"A Practical Guide to Building Agents" | 功能可靠性、集成协同 |
| OpenAPI Specification 3.0+ | 可发现性、一致性 |
| IETF RFC 7807 | 错误质量 |
| APIContext — API Drift 白皮书 | 一致性检测、阈值基线 |
| Salt Security 安全报告 | 安全就绪 |
| Gravitee 调查 | 流量韧性 |