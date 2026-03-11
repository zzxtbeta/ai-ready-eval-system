"""
AI-Ready Eval System — CLI 入口

用法：
  python main.py eval-api --spec examples/sample_api_spec.yaml
  python main.py eval-skill --skill examples/sample_skill.md
  python main.py eval-all
  python main.py dashboard
  python main.py check-gate --min-api-score 0.70
"""

import sys
import os
import json
import datetime
import click
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration file."""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def grade(score: float) -> str:
    """Convert numeric score to letter grade."""
    if score >= 0.85:
        return "A"
    elif score >= 0.70:
        return "B"
    elif score >= 0.50:
        return "C"
    else:
        return "D"


def grade_color(g: str) -> str:
    return {"A": "green", "B": "yellow", "C": "orange1", "D": "red"}.get(g, "white")


@click.group()
def cli():
    """AI-Ready Eval System — API & Skill Quality Evaluator"""
    pass


@cli.command("eval-api")
@click.option("--spec", default=None, help="OpenAPI spec 路径（YAML/JSON）")
@click.option("--base-url", default=None, help="API base URL（动态探测）")
@click.option("--output", default="reports", help="报告输出目录")
@click.option("--config", default="config.yaml", help="配置文件路径")
@click.option("--static-only", is_flag=True, default=False, help="仅静态分析，不发实际请求")
def eval_api(spec, base_url, output, config, static_only):
    """评估 API 的 AI-Readiness"""
    cfg = load_config(config)
    
    spec_path = spec or cfg.get("api_eval", {}).get("openapi_spec_path", "")
    api_base_url = base_url or cfg.get("api_eval", {}).get("base_url", "")
    
    if not spec_path:
        console.print("[red]错误：请提供 OpenAPI spec 路径（--spec 或在 config.yaml 中配置）[/red]")
        sys.exit(1)
    
    console.print(Panel(f"[bold cyan]API AI-Readiness 评估[/bold cyan]\nSpec: {spec_path}"))
    
    from api_eval.scanner import APIScanner
    from api_eval.report import APIReport
    
    # 静态分析
    with console.status("[bold green]正在进行静态分析..."):
        scanner = APIScanner(spec_path)
        static_results = scanner.run()
    
    all_results = {"static": static_results, "dynamic": {}, "agent_trial": {}}
    
    # 动态探测
    if not static_only and api_base_url:
        from api_eval.prober import APIProber
        with console.status("[bold green]正在进行动态探测..."):
            prober = APIProber(spec_path, api_base_url, cfg.get("api_eval", {}).get("probe", {}))
            all_results["dynamic"] = prober.run()
    
    # 生成报告
    report = APIReport(all_results)
    report_data = report.build()
    
    # 保存报告
    os.makedirs(output, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output, f"api_report_{ts}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    # 同时保存为 latest
    latest_path = os.path.join(output, "api_report_latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    # 展示结果
    _display_api_results(report_data)
    console.print(f"\n[dim]报告已保存：{report_path}[/dim]")


@cli.command("eval-skill")
@click.option("--skill", default=None, multiple=True, help="Skill 文件路径（可多次指定）")
@click.option("--output", default="reports", help="报告输出目录")
@click.option("--config", default="config.yaml", help="配置文件路径")
def eval_skill(skill, output, config):
    """评估 Skill 的质量"""
    cfg = load_config(config)
    
    skill_paths = list(skill) or cfg.get("skill_eval", {}).get("skill_paths", [])
    if not skill_paths:
        console.print("[red]错误：请提供 Skill 文件路径（--skill 或在 config.yaml 中配置）[/red]")
        sys.exit(1)
    
    console.print(Panel(f"[bold magenta]Skill 质量评估[/bold magenta]\nSkills: {', '.join(skill_paths)}"))
    
    from skill_eval.structure_check import StructureChecker
    from skill_eval.content_analysis import ContentAnalyzer
    from skill_eval.report import SkillReport
    
    all_skill_results = []
    for path in skill_paths:
        with console.status(f"[bold green]评估 Skill: {path}..."):
            checker = StructureChecker(path)
            struct_result = checker.run()
            
            analyzer = ContentAnalyzer(path)
            content_result = analyzer.run()
            
            all_skill_results.append({
                "path": path,
                "structure": struct_result,
                "content": content_result
            })
    
    report = SkillReport(all_skill_results)
    report_data = report.build()
    
    os.makedirs(output, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output, f"skill_report_{ts}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    latest_path = os.path.join(output, "skill_report_latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    _display_skill_results(report_data)
    console.print(f"\n[dim]报告已保存：{report_path}[/dim]")


@cli.command("eval-all")
@click.option("--output", default="reports", help="报告输出目录")
@click.option("--config", default="config.yaml", help="配置文件路径")
def eval_all(output, config):
    """运行全量评估（API + Skill）"""
    from click import Context
    ctx = click.get_current_context()
    cfg = load_config(config)
    
    console.print(Panel("[bold]AI-Ready Eval — 全量评估[/bold]", border_style="cyan"))
    
    spec_path = cfg.get("api_eval", {}).get("openapi_spec_path", "")
    if spec_path:
        ctx.invoke(eval_api, spec=spec_path, output=output, config=config)
    
    skill_paths = cfg.get("skill_eval", {}).get("skill_paths", [])
    if skill_paths:
        ctx.invoke(eval_skill, skill=tuple(skill_paths), output=output, config=config)


@cli.command("dashboard")
@click.option("--host", default="0.0.0.0", help="监听地址")
@click.option("--port", default=5000, help="监听端口")
@click.option("--reports-dir", default="reports", help="报告目录")
def dashboard(host, port, reports_dir):
    """启动可视化仪表盘"""
    os.environ["REPORTS_DIR"] = reports_dir
    from dashboard.app import app
    console.print(Panel(f"[bold cyan]仪表盘启动[/bold cyan]\n访问 http://{host}:{port}"))
    app.run(host=host, port=port, debug=False)


@cli.command("check-gate")
@click.option("--min-api-score", default=0.70, help="API 评分门禁（低于此值报错）")
@click.option("--min-skill-score", default=0.70, help="Skill 评分门禁")
@click.option("--reports-dir", default="reports", help="报告目录")
def check_gate(min_api_score, min_skill_score, reports_dir):
    """CI/CD 质量门禁检查"""
    failed = False
    
    api_report_path = os.path.join(reports_dir, "api_report_latest.json")
    if os.path.exists(api_report_path):
        with open(api_report_path) as f:
            api_data = json.load(f)
        api_score = api_data.get("overall_score", 0)
        g = grade(api_score)
        color = grade_color(g)
        console.print(f"API Score: [{color}]{api_score:.2f} ({g})[/{color}]")
        if api_score < min_api_score:
            console.print(f"[red]✗ API 评分 {api_score:.2f} < 门禁阈值 {min_api_score}[/red]")
            failed = True
        else:
            console.print(f"[green]✓ API 评分通过[/green]")
    
    skill_report_path = os.path.join(reports_dir, "skill_report_latest.json")
    if os.path.exists(skill_report_path):
        with open(skill_report_path) as f:
            skill_data = json.load(f)
        skill_score = skill_data.get("overall_score", 0)
        g = grade(skill_score)
        color = grade_color(g)
        console.print(f"Skill Score: [{color}]{skill_score:.2f} ({g})[/{color}]")
        if skill_score < min_skill_score:
            console.print(f"[red]✗ Skill 评分 {skill_score:.2f} < 门禁阈值 {min_skill_score}[/red]")
            failed = True
        else:
            console.print(f"[green]✓ Skill 评分通过[/green]")
    
    if failed:
        sys.exit(1)


def _display_api_results(report_data: dict):
    """在终端展示 API 评估结果摘要。"""
    overall = report_data.get("overall_score", 0)
    g = grade(overall)
    
    console.print(f"\n[bold]API AI-Readiness Score: {overall:.2f} — 等级 {g}[/bold]")
    
    table = Table(box=box.ROUNDED, show_header=True)
    table.add_column("维度", style="cyan")
    table.add_column("得分", justify="right")
    table.add_column("等级", justify="center")
    table.add_column("关键问题")
    
    for dim in report_data.get("dimensions", []):
        s = dim.get("score", 0)
        g_dim = grade(s)
        color = grade_color(g_dim)
        issues = "; ".join(dim.get("issues", [])[:2]) or "—"
        table.add_row(
            dim.get("name", ""),
            f"{s:.2f}",
            f"[{color}]{g_dim}[/{color}]",
            issues
        )
    
    console.print(table)


def _display_skill_results(report_data: dict):
    """在终端展示 Skill 评估结果摘要。"""
    overall = report_data.get("overall_score", 0)
    g = grade(overall)
    
    console.print(f"\n[bold]Skill Quality Score: {overall:.2f} — 等级 {g}[/bold]")
    
    table = Table(box=box.ROUNDED, show_header=True)
    table.add_column("维度", style="magenta")
    table.add_column("得分", justify="right")
    table.add_column("等级", justify="center")
    table.add_column("关键问题")
    
    for dim in report_data.get("dimensions", []):
        s = dim.get("score", 0)
        g_dim = grade(s)
        color = grade_color(g_dim)
        issues = "; ".join(dim.get("issues", [])[:2]) or "—"
        table.add_row(
            dim.get("name", ""),
            f"{s:.2f}",
            f"[{color}]{g_dim}[/{color}]",
            issues
        )
    
    console.print(table)


if __name__ == "__main__":
    cli()
