# AI-Ready Eval System

> Skills 质量 + API 就绪度 · 统一评估系统
>
> 面向开源的通用评估框架

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

---

## 为什么需要这套系统

Agent 时代的基础设施有两层：**数据接口层**（API）和**工作流层**（Skills）。这套系统统一评估两层质量：

1. **API AI-Readiness Score** — 一个 API 对 agent 来说是否好用？
2. **Skill Quality Score** — 一个 Skill 在生产环境中是否可靠？
3. **Integration Score** — API + Skill 协同时，端到端体验是否合格？

## 快速开始

### 安装

```bash
git clone https://github.com/your-org/ai-ready-eval
cd ai-ready-eval
pip install -r requirements.txt
```

### 配置

编辑 `config.yaml`，填入你的 API endpoint 和 Skill 路径：

```yaml
api_eval:
  openapi_spec_path: "examples/sample_api_spec.yaml"
  base_url: "https://api.example.com"

skill_eval:
  skill_paths:
    - "examples/sample_skill.md"

llm:
  provider: "openai"
  model: "gpt-4o"
  api_key: "${OPENAI_API_KEY}"
```

### 运行评估

```bash
# 运行 API 评估
python main.py eval-api --spec examples/sample_api_spec.yaml

# 运行 Skill 评估
python main.py eval-skill --skill examples/sample_skill.md

# 运行全量评估并启动仪表盘
python main.py eval-all
python main.py dashboard
```

### 访问仪表盘

```bash
python main.py dashboard
# 访问 http://localhost:5000
```

## 架构

```
ai-ready-eval/
├── api_eval/          # API AI-Readiness 评估
│   ├── scanner.py     # 静态扫描（OpenAPI spec 分析）
│   ├── prober.py      # 动态探测（实际调用 API）
│   ├── agent_trial.py # Agent 试用（LLM 执行任务）
│   └── dimensions/    # 8 个评估维度
├── skill_eval/        # Skill 质量评估
│   ├── structure_check.py
│   ├── content_analysis.py
│   ├── trigger_eval.py
│   └── functional_eval.py
├── dashboard/         # 统一可视化仪表盘（Flask）
├── examples/          # 示例 API spec + Skill
└── reports/           # 评估结果存档
```

## 评分体系

| 等级 | 分数 | API 含义 | Skill 含义 |
|------|------|---------|-----------|
| A | ≥ 0.85 | Agent-Ready | Production-Grade |
| B | ≥ 0.70 | Agent-Usable | Usable |
| C | ≥ 0.50 | Agent-Fragile | Fragile |
| D | < 0.50 | Agent-Hostile | Prototype |

## API 评估维度

1. **语义描述完整性** — 端点、参数、响应描述覆盖率
2. **响应体量控制** — 默认响应大小、分页支持
3. **错误语义质量** — 错误结构化、诊断可用性
4. **可发现性** — OpenAPI spec 可访问性、MCP 支持
5. **工作流文档化** — 多步调用链文档
6. **设计一致性** — 命名、格式、认证统一性
7. **流量韧性** — Rate limit、突发流量处理
8. **安全就绪** — OAuth2、最小权限、scope 支持

## Skill 评估维度

1. **结构合规** — 行数、Frontmatter、分层
2. **指令质量** — 解释率、示例覆盖、边界处理
3. **触发准确率** — Should/should-not trigger eval
4. **功能可靠性** — Assertion 通过率、定性评分
5. **集成协同** — 多 skill 编排正确性

## CI/CD 集成

```yaml
# .github/workflows/eval.yml
- name: Run AI-Ready Eval
  run: |
    python main.py eval-all --output reports/
    python main.py check-gate --min-api-score 0.70 --min-skill-score 0.70
```

## 许可

MIT License — 详见 [LICENSE](LICENSE)
