# AI-Ready Eval

> Skills 质量 + API 就绪度 · 统一评估系统 Spec
>
> 面向开源的通用评估框架

---

## 为什么需要这套系统

Agent 时代的基础设施有两层：**数据接口层**（API）和**工作流层**（Skills）。两层各自有质量标准，且必须协同工作。但目前行业缺少一套统一的、可量化的方法来评估这两层——大多数团队还在"跑一下看着差不多就行"的阶段。

这套系统解决三个问题：

1. **一个 API 对 agent 来说是否好用？** — API AI-Readiness Score
2. **一个 Skill 在生产环境中是否可靠？** — Skill Quality Score
3. **API + Skill 协同时，端到端体验是否合格？** — Integration Score

---

## 设计原则

**Eval-Driven，不是 Checklist-Driven。** Checklist 告诉你"应该做什么"，Eval 告诉你"实际做到了多少"。我们提供 checklist 作为指引，但最终评分基于 agent 实际调用的成功率和输出质量。

**通用框架，不绑定特定领域。** 评估维度和方法论适用于任何行业的 API 和 Skill，不预设业务场景。用户通过配置文件定义自己的 API endpoint 和 Skill 文件路径。

**渐进式采纳。** 可以只用 API 评估模块，也可以只用 Skill 评估模块，也可以两者联合使用。每个模块独立运行，合在一起时通过统一仪表盘呈现。

**来源可追溯。** 每个评估维度都标注其理论依据——来自 The New Stack 的行业实践、Anthropic skill-creator 的工程规范、OpenAI Agent 构建白皮书、还是 OpenAPI Specification 标准。

---

## 整体架构

```
ai-ready-eval/
├── README.md
├── config.yaml                     # 用户配置：API endpoint、Skill 路径、模型选择
│
├── api_eval/                       # 模块一：API AI-Readiness 评估
│   ├── scanner.py                  # 静态扫描：OpenAPI spec 分析
│   ├── prober.py                   # 动态探测：实际调用 API 并分析行为
│   ├── agent_trial.py              # Agent 试用：让真实 agent 执行任务
│   ├── dimensions/                 # 评估维度定义（每个维度一个文件）
│   │   ├── semantic_description.py
│   │   ├── response_sizing.py
│   │   ├── error_quality.py
│   │   ├── discoverability.py
│   │   ├── workflow_documentation.py
│   │   ├── design_consistency.py
│   │   ├── traffic_resilience.py
│   │   └── security_readiness.py
│   └── report.py                   # 报告生成
│
├── skill_eval/                     # 模块二：Skill 质量评估
│   ├── structure_check.py          # 结构检查：文件组织、行数、分层
│   ├── content_analysis.py         # 内容分析：规则风格、语义清晰度
│   ├── trigger_eval.py             # 触发评估：should/should-not trigger
│   ├── functional_eval.py          # 功能评估：用真实 prompt 执行 skill
│   ├── integration_eval.py         # 集成评估：多 skill 协同
│   └── report.py
│
├── dashboard/                      # 统一仪表盘
│   ├── app.py                      # 本地 Web 服务
│   ├── templates/
│   └── static/
│
├── reports/                        # 评估结果存档
│   └── {timestamp}/
│       ├── api_report.json
│       ├── skill_report.json
│       └── summary.html
│
└── docs/
    ├── dimensions_reference.md     # 所有评估维度的详细定义
    ├── scoring_methodology.md      # 评分方法论
    └── contributing.md             # 开源贡献指南
```

---

## 模块一：API AI-Readiness 评估

### 评估理念

传统 API 测试问的是"这个接口按规格工作吗"（correctness）。AI-Readiness 评估问的是一个完全不同的问题："一个 LLM agent 能不能理解并正确使用这个接口"（usability-for-agents）。

这意味着评估必须包含三个层次：

| 层次 | 问什么 | 怎么测 |
|------|--------|--------|
| **静态分析** | 接口描述对 agent 来说是否可读 | 解析 OpenAPI spec，检查描述完整性 |
| **动态探测** | 接口行为对 agent 来说是否可预测 | 发送各种请求，分析响应特征 |
| **Agent 试用** | 真实 agent 能不能完成任务 | 给 agent 一个任务目标，看它能否通过调用 API 完成 |

---

### 维度 1：语义描述完整性（Semantic Description）

**理论依据**：The New Stack 引用 Tyk CEO 的观点——LLM 依赖的是描述性规范，不只是结构，而是需要上下文丰富的描述。APIContext 2024 报告指出 75% 的生产 API 存在 spec 与实际行为不一致的问题。

**为什么重要**：Agent 不会读代码、不会看 Postman Collection、不会问同事"这个参数啥意思"。它完全依赖 OpenAPI spec 中的 description 字段来理解每个端点、参数和响应的含义。描述缺失或模糊 = agent 调用失败或幻觉。

**评估项**：

| 检查项 | 权重 | 判定标准 | 失败含义 |
|--------|------|---------|---------|
| 端点描述覆盖率 | 高 | 每个 path + method 都有 description 且 > 15 词 | Agent 不知道这个端点干什么 |
| 参数描述覆盖率 | 高 | 每个参数都有 description 且含语义说明（不只是类型声明） | Agent 不知道传什么值 |
| 参数示例覆盖率 | 中 | 每个参数有 example 或 enum 值 | Agent 猜测参数格式 |
| 响应字段描述率 | 中 | 响应 schema 的每个字段都有 description | Agent 不知道返回值含义 |
| 描述质量评分 | 高 | 用 LLM 评估描述是否足够让 agent 理解用途（非重复、非套话） | 有描述但没用 |

**静态检测方法**：解析 OpenAPI spec，遍历 paths → operations → parameters → responses，对每个元素检查 description 字段，统计覆盖率，并用 LLM 对描述质量打分（1-5）。

**Agent 试用方法**：给 agent 仅提供 OpenAPI spec（不提供额外文档），要求它"用这个 API 完成 [任务]"。如果 agent 调用了错误的端点或传了错误的参数 → 描述不足的证据。

---

### 维度 2：响应体量控制（Response Sizing）

**理论依据**：The New Stack 引用专家建议暴露"chunky"的工具——组合端点实现业务目标，而不是暴露原始 CRUD。OpenAI Agent 白皮书强调 agent 需要最小化每步获取的信息量以保持推理质量。

**为什么重要**：一个 API 默认返回 500 条记录的完整 JSON，对人类前端无所谓（前端做分页），但对 agent 来说可能直接导致上下文溢出、推理能力下降、后续步骤全部出错。

**评估项**：

| 检查项 | 权重 | 判定标准 | 失败含义 |
|--------|------|---------|---------|
| 默认响应体积 | 高 | 无参数调用时，响应 < 4KB（约 1K token） | 默认返回量可能撑爆 context |
| 分页支持 | 高 | 列表端点支持 page/limit 或 cursor 分页 | Agent 无法控制获取量 |
| 字段筛选 | 中 | 支持 fields/select 参数选择返回字段 | 每次都返回全量字段 |
| 摘要模式 | 低 | 提供 summary/detail 两种响应模式 | 无法按需获取精简版 |
| 批量端点 | 低 | 高频多次调用的场景有批量接口 | Agent 被迫循环调用 |

**动态探测方法**：对每个 GET 端点——无参数调用测量体积（bytes + 估算 token 数）；有分页参数调用验证分页工作；带 fields 参数验证字段筛选。记录每个端点的 "agent-safe 默认响应量"。

---

### 维度 3：错误语义质量（Error Quality）

**理论依据**：The New Stack 引用 Microsoft 产品经理的建议——每个错误码都应提供定义、下一步动作建议、常见失败案例。引用 Zuplo 工程师建议返回 RFC 7807 problem+json 格式。

**为什么重要**：Agent 出错后需要自我修正。如果错误响应只有 `{"error": "Bad Request"}`，agent 无法知道哪里错了、该怎么改。好的错误响应 = agent 的自愈能力。

**评估项**：

| 检查项 | 权重 | 判定标准 | 失败含义 |
|--------|------|---------|---------|
| 错误响应结构化 | 高 | 错误响应是 JSON 且有固定结构（非纯文本/HTML） | Agent 无法解析错误 |
| 错误码语义区分 | 高 | 不同类型错误返回不同状态码（400/401/404/422） | Agent 无法区分错误类型 |
| 错误消息具体性 | 高 | 消息指出具体哪个参数/字段有问题 | Agent 不知道改哪里 |
| 修复建议 | 中 | 错误响应包含 suggested_fix 或 next_action | Agent 需要额外推理修复方案 |
| RFC 7807 兼容 | 低 | 使用 application/problem+json 媒体类型 | 未遵循标准 |

**动态探测方法**：对每个端点构造错误场景——缺少必填参数、参数类型错误、无效枚举值、无权限、资源不存在——检查响应是否结构化、是否指出具体问题、是否提供修复建议。

---

### 维度 4：可发现性（Discoverability）

**理论依据**：The New Stack 引用 Exa 联合创始人——API 经济不再是"谁的 DevRel 最好"，而是"谁让自己对机器最可读"。文章讨论了 MCP Server、llms.txt、Arazzo 等发现机制。Nordic APIs 梳理了 7 种 agent-to-API 标准（MCP、A2A、agents.json、ACP 等）。

**为什么重要**：Agent 首先需要"找到"你的 API，然后"理解"它能做什么。没有标准化发现入口，agent 可能根本不知道它的存在。

**评估项**：

| 检查项 | 权重 | 判定标准 | 失败含义 |
|--------|------|---------|---------|
| OpenAPI spec 可访问 | 高 | spec 文件有公开可访问的 URL | Agent 工具链无法自动导入 |
| Spec 格式有效性 | 高 | 通过 OpenAPI 3.0+ validator 校验无错误 | 自动解析工具会失败 |
| MCP Server 支持 | 中 | 提供 MCP server 封装 | Agent 需要手动集成 |
| llms.txt 文件 | 低 | 根目录有 llms.txt | 被 AI 爬虫发现概率降低 |
| Spec-实现一致性 | 高 | 实际 API 行为与 spec 描述一致（无 drift） | Agent 按 spec 调用但实际失败 |

**检测方法**：静态验证 spec 格式合法性；动态对 spec 中每个端点发请求，验证端点存在、返回结构与 schema 一致、必填参数确实必填。

---

### 维度 5：工作流文档化（Workflow Documentation）

**理论依据**：The New Stack 讨论了 Arazzo 规范用于文档化多步 API 操作，以及 HATEOAS 风格帮助 agent 理解下一步。OpenAI Agent 白皮书强调 agent 需要理解"在什么状态下调用什么工具"。

**为什么重要**：Agent 经常需要串联多个 API 调用来完成一个任务。如果没有文档化调用链，agent 需要自己推断，成功率显著下降。

**评估项**：

| 检查项 | 权重 | 判定标准 | 失败含义 |
|--------|------|---------|---------|
| 多步工作流文档 | 中 | 提供常见工作流的步骤说明 | Agent 必须自己推断调用顺序 |
| 响应含下一步提示 | 低 | 响应中包含 HATEOAS 风格链接或 next_action | Agent 无法从响应推断后续步骤 |
| 端点间依赖说明 | 中 | Spec 描述中注明前置依赖 | Agent 可能跳步调用导致失败 |

---

### 维度 6：设计一致性（Design Consistency）

**理论依据**：The New Stack 引用 Tyk CEO——LLM 是模式追随者。Netlify 产品经理指出可选字段的不一致处理是 agent 错误的常见来源。

**为什么重要**：Agent 从成功调用中学习模式并外推到后续调用。不一致的设计会导致模式外推失败。

**评估项**：

| 检查项 | 权重 | 判定标准 | 失败含义 |
|--------|------|---------|---------|
| 命名一致性 | 中 | 字段命名风格统一（全 camelCase 或全 snake_case） | Agent 猜错字段名 |
| 分页风格统一 | 中 | 所有列表端点使用相同分页参数名和结构 | 每个端点需单独学习 |
| 日期格式统一 | 中 | 所有日期字段使用同一格式（ISO 8601） | Agent 构造的日期格式错误 |
| 认证方式统一 | 高 | 所有端点使用同一认证方式 | 需处理多种认证逻辑 |
| 可选字段行为统一 | 中 | 可选字段缺失时行为一致 | 不可预测行为导致 agent 不稳定 |

**检测方法**：静态分析 spec——提取所有字段名检查命名风格、提取所有列表端点参数检查分页统一、提取所有日期字段检查 format 标注。

---

### 维度 7：流量韧性（Traffic Resilience）

**理论依据**：The New Stack 引用 APIContext COO——agent 行为不同于人类用户。Gravitee 调查显示 82% 美国公司遇到过 agent "失控"。Nordic APIs 讨论了 just-in-time authorization 概念。

**为什么重要**：Agent 可能短时间高频调用或因推理错误无限重试。API 需要优雅处理这种模式。

**评估项**：

| 检查项 | 权重 | 判定标准 | 失败含义 |
|--------|------|---------|---------|
| Rate limit 响应头 | 高 | 响应包含 X-RateLimit-Remaining 等标准头 | Agent 不知道剩余配额 |
| 限流响应可解读 | 高 | 429 响应包含 Retry-After 头或 body | Agent 不知道该等多久 |
| 突发流量容忍 | 中 | 10 QPS 短时突发不会导致服务降级 | Agent 正常节奏就触发限流 |
| 批量操作支持 | 低 | 提供批量端点减少调用次数 | Agent 被迫高频单条调用 |

**动态探测方法**：以 1 QPS 发 10 请求（基线）→ 以 10 QPS 发 10 请求（突发）→ 检查 429 响应头 → 验证恢复正常。

---

### 维度 8：安全就绪（Security Readiness）

**理论依据**：Salt Security 报告 95% API 攻击来自已认证来源。Nordic APIs 2026 预测强调 agent 权限委托和最小权限原则。

**为什么重要**：Agent 代表用户调用 API，但权限应受限。缺少细粒度权限控制 = 被注入恶意指令的 agent 可能越权。

**评估项**：

| 检查项 | 权重 | 判定标准 | 失败含义 |
|--------|------|---------|---------|
| 认证标准化 | 高 | 使用 OAuth 2.0 / API Key 等标准方式 | Agent 工具链无法自动认证 |
| 最小权限支持 | 高 | 支持 scope/角色区分读/写/管理 | Agent 获得过大权限 |
| 敏感数据标记 | 中 | 敏感字段有标记或可排除 | Agent 可能暴露敏感数据 |
| API inventory 完整 | 中 | 所有端点都在 spec 中（无 shadow API） | Agent 可能发现未保护端点 |

---

### API AI-Readiness 综合评分

```
总分 = Σ(维度分 × 维度权重) / Σ(维度权重)

每个维度分 = Σ(检查项分 × 检查项权重) / Σ(检查项权重)

检查项分：Pass = 1.0 / Partial = 0.5 / Fail = 0.0

等级映射：
  ≥ 0.85 → A（Agent-Ready：可直接供 agent 使用）
  ≥ 0.70 → B（Agent-Usable：基本可用，部分场景需兜底）
  ≥ 0.50 → C（Agent-Fragile：勉强可用，高失败率）
  < 0.50 → D（Agent-Hostile：不建议供 agent 使用）
```

---

## 模块二：Skill 质量评估

### 评估理念

参照 Anthropic skill-creator 的工程规范和 OpenAI Agent 白皮书的设计原则。生产级 Skill 需要：结构合理、触发准确、输出可靠、可持续迭代。

---

### 维度 1：结构合规（Structure）

**理论依据**：Anthropic skill-creator 的渐进式加载原则——metadata 始终在 context（约 100 词）、SKILL.md 触发时加载（< 500 行）、resources 按需加载。

**为什么重要**：SKILL.md 越长 → context window 占用越大 → 实际推理空间越小。这和 API 的"响应体量控制"是同一个问题——都是 context window 管理。

**评估项**：

| 检查项 | 权重 | 判定标准 |
|--------|------|---------|
| SKILL.md 行数 | 高 | < 500 行（理想 < 200 行） |
| Frontmatter 完整性 | 高 | 有 name + description；description > 30 词 |
| 分层合理性 | 高 | 详细规范在 references/，SKILL.md 只放核心逻辑 |
| References 有指引 | 中 | SKILL.md 中明确说明何时读取哪个 reference |
| 无硬编码业务数据 | 中 | 不含会过时的具体数据 |

---

### 维度 2：指令质量（Instruction Quality）

**理论依据**：Anthropic skill-creator——"大量 ALWAYS/NEVER 是黄色信号，试着解释为什么。" OpenAI 白皮书——"break tasks into discrete steps and anticipate edge cases"。

**为什么重要**：解释式指令让 agent 理解意图，在未预见场景中也能合理判断；命令式规则堆叠会导致冲突和僵化。

**评估项**：

| 检查项 | 权重 | 判定标准 |
|--------|------|---------|
| 命令式规则密度 | 中 | "禁止/必须/MUST/NEVER" 频率 < 每 50 行 1 次 |
| Why 解释率 | 高 | ≥ 50% 的约束性规则附带理由 |
| 示例覆盖 | 中 | 关键行为有正面 + 反面示例 |
| 边界条件处理 | 高 | 明确说明数据不足/异常/冲突时的行为 |
| 输出格式清晰度 | 中 | 输出模板有明确结构，说明可省略部分 |

---

### 维度 3：触发准确率（Trigger Accuracy）

**理论依据**：Anthropic skill-creator 完整流程——构造 should/should-not trigger eval 集，分 60% 训练 / 40% 测试，迭代 5 轮优化 description。

**为什么重要**：Description 是 agent "要不要用这个 skill"的唯一依据。太宽 = 误触发；太窄 = 该用时没用上。

**评估项**：

| 检查项 | 权重 | 判定标准 |
|--------|------|---------|
| Should-trigger 准确率 | 高 | > 90% 正例正确触发 |
| Should-not-trigger 准确率 | 高 | > 90% 反例未触发 |
| Edge case 覆盖 | 中 | 含模糊措辞、近义表达、跨语言 |
| Eval 集规模 | 中 | ≥ 20 条（10 正 + 10 反） |

---

### 维度 4：功能可靠性（Functional Reliability）

**理论依据**：Anthropic skill-creator 核心循环——起草→测试→评估（定性+定量）→迭代。OpenAI 白皮书——"start with the most capable models to establish performance baselines"。

**为什么重要**：Skill 声称能做的事实际能不能做到、做到什么质量，需要真实任务 prompt 验证。

**评估项**：

| 检查项 | 权重 | 判定标准 |
|--------|------|---------|
| Eval 用例覆盖 | 高 | 核心场景、边缘场景、异常场景均有 |
| 定量 Assertion 通过率 | 高 | > 80% |
| 定性评审评分 | 高 | 人类评审 > 3.5/5 |
| Baseline 对比 | 中 | 有 skill vs 无 skill 输出对比 |
| 迭代历史 | 低 | 有多轮迭代记录 |

---

### 维度 5：集成协同（Integration）

**理论依据**：OpenAI 白皮书——Manager pattern 和 Decentralized pattern 两种多 agent 编排。

**为什么重要**：单 skill 隔离环境表现好 ≠ 多 skill 协同正常。数据格式不匹配、调用顺序假设不一致、重复调用同一 API 等只在集成时暴露。

**评估项**：

| 检查项 | 权重 | 判定标准 |
|--------|------|---------|
| 编排路由正确性 | 高 | 编排 skill 正确分发给对的子 skill |
| 子 skill 输出兼容性 | 高 | 子 skill 输出能被编排层正确消费 |
| 矛盾数据处理 | 中 | 多源矛盾信息有处理策略 |
| 端到端完成率 | 高 | 从用户 prompt 到最终输出的成功率 |

---

### Skill Quality 综合评分

```
评分方法同 API AI-Readiness。

等级映射：
  ≥ 0.85 → A（Production-Grade）
  ≥ 0.70 → B（Usable，需人工抽检）
  ≥ 0.50 → C（Fragile，高频出错）
  < 0.50 → D（Prototype，不建议生产使用）
```

---

## 统一仪表盘

### 核心视图

**概览页**：API Readiness Score + Skill Quality Score + 上次评估时间 + 趋势图

**API 详情页**：每个维度得分 + 每个检查项 pass/partial/fail + 失败项诊断 + 修复建议优先排序

**Skill 详情页**：每个维度得分 + eval 逐条结果 + 触发准确率矩阵 + 结构合规清单

**趋势页**：历次评估对比，识别退化

### 报告导出

- **JSON**：供 CI/CD 消费，可设质量门禁（如"API Readiness < B 则阻断"）
- **HTML**：独立可视化报告，可直接用于客户交流

---

## 给 Claude Code 的执行指令

```markdown
# 任务：构建 AI-Ready Eval 系统

读取本 spec 后，按以下阶段逐步实现。
每阶段完成后向我确认再进下一阶段。

## 阶段 1：项目初始化
1. 创建目录结构
2. 创建 config.yaml 模板（含注释）
3. 创建 README.md（介绍 + 快速开始 + 架构图）
4. 安装依赖：pyyaml, openapi-spec-validator, requests, jinja2, flask

## 阶段 2：API 评估 - 静态分析
实现 api_eval/scanner.py：
- 维度 1（语义描述）静态检查
- 维度 4（可发现性）spec 格式验证
- 维度 6（设计一致性）命名/格式/分页统一性
- 输出结构化 JSON

## 阶段 3：API 评估 - 动态探测
实现 api_eval/prober.py：
- 维度 2（响应体量）实际调用测试
- 维度 3（错误质量）错误场景构造
- 维度 7（流量韧性）突发流量测试
- 维度 8（安全就绪）认证权限检查

## 阶段 4：API 评估 - Agent 试用
实现 api_eval/agent_trial.py：
- 接受任务描述 + OpenAPI spec
- 调用 LLM 尝试完成任务
- 记录调用链（端点、参数、成功/失败）
- 分析失败原因
- 这是最有价值的测试层

## 阶段 5：Skill 评估 - 结构和内容
实现 structure_check.py + content_analysis.py：
- 解析 frontmatter + 统计行数
- 分析规则密度和 why 解释率
- 评估示例覆盖和边界条件

## 阶段 6：Skill 评估 - 触发和功能
实现 trigger_eval.py + functional_eval.py：
- 触发评估：LLM 判断触发正确性
- 功能评估：执行 prompt + 运行 assertions
- 支持 baseline 对比

## 阶段 7：统一仪表盘
实现 dashboard/：
- Flask 应用
- 概览 + API详情 + Skill详情 + 趋势
- JSON + HTML 报告导出

## 阶段 8：开源准备
- 完善文档
- LICENSE (MIT)
- Issue / PR template
- contributing.md

## 验收标准（每阶段）
- 代码可运行，有基本错误处理
- 有使用示例（mock API spec + mock skill 演示）
- 关键函数有 docstring
- 输出结构化 JSON
```

---

## 参考来源索引

| 来源 | 影响的维度 |
|------|----------|
| The New Stack — "How To Prepare Your API for AI Agents" (2025-06) | 语义描述、响应体量、错误质量、可发现性、工作流文档、设计一致性、流量韧性、安全就绪 |
| The New Stack — "Why Most APIs Fail in AI Systems" (2026-01) | 语义描述、spec-实现一致性 |
| Nordic APIs — "10 AI-Driven API Economy Predictions for 2026" | 安全就绪（JIT authorization）、MCP 成熟度 |
| Nordic APIs — "Comparing 7 AI Agent-to-API Standards" (2025-06) | 可发现性（MCP/A2A/agents.json 等） |
| Anthropic — skill-creator SKILL.md 工程规范 | 结构合规、指令质量、触发准确率、功能可靠性 |
| OpenAI — "A Practical Guide to Building Agents" (2025-04) | 功能可靠性、集成协同、工作流文档 |
| OpenAPI Specification 3.0+ | 可发现性、设计一致性 |
| IETF RFC 7807 — Problem Details for HTTP APIs | 错误质量 |
| APIContext — API Drift 白皮书 (2024) | Spec-实现一致性 |
| Salt Security — API 安全报告 | 安全就绪 |
| Gravitee — Agent "失控" 调查 | 流量韧性 |
| IDC FutureScape 2025 | AI-Ready 数据平台 |