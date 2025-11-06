"""
B-gent CLI

DFIR 자동화 에이전트 실행 프로그램
"""
import sys
import os
import atexit
import logging
import json

os.environ["TOKENIZERS_PARALLELISM"] = "false"

os.environ["LOGLEVEL"] = "CRITICAL"
os.environ["LOG_LEVEL"] = "CRITICAL"
os.environ["PYTHONWARNINGS"] = "ignore"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

if os.getenv("MCP_DEBUG") == "1":
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')
else:
    logging.basicConfig(level=logging.CRITICAL, format='%(message)s', force=True)

root_logger = logging.getLogger()
root_logger.setLevel(logging.CRITICAL)
root_logger.disabled = True

for logger_name in ["urllib3", "pymongo", "httpx", "mcp", "transformers",
                    "elastic_transport", "markdown_it", "src.server", "FastMCP",
                    "pyghidra_mcp", "mcp.server.lowlevel.server", "mcp.server",
                    "FastMCP.fastmcp.server.server", "root"]:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.CRITICAL)
    logger.disabled = True
    logger.propagate = False
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich import box
from rich.layout import Layout
from rich.text import Text
from rich.live import Live
from rich.align import Align
import time
from datetime import datetime
from agent.core.router import run_job, WORKFLOW_MODE

console = Console()
current_step = ""
step_history = []
phase_timings = {}

def print_agent_state_update(state_doc: dict):
    """AGENT_STATES 업데이트 내용을 JSON으로 출력

    Args:
        state_doc: MongoDB에 저장된 state 문서
    """
    display_doc = {k: v for k, v in state_doc.items() if k != '_id'}

    if 'created_at' in display_doc:
        display_doc['created_at'] = display_doc['created_at'].isoformat() if hasattr(display_doc['created_at'], 'isoformat') else str(display_doc['created_at'])
    if 'updated_at' in display_doc:
        display_doc['updated_at'] = display_doc['updated_at'].isoformat() if hasattr(display_doc['updated_at'], 'isoformat') else str(display_doc['updated_at'])

    json_str = json.dumps(display_doc, indent=2, ensure_ascii=False)
    print(json_str)

class SuppressOutput:
    """표준 출력/에러 억제"""
    def __enter__(self):
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr

def print_banner():
    """배너 출력"""
    banner = """
    ██████╗         ██████╗ ███████╗███╗   ██╗████████╗
    ██╔══██╗       ██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
    ██████╔╝ ████╗ ██║  ███╗█████╗  ██╔██╗ ██║   ██║
    ██╔══██╗ ╚═══╝ ██║   ██║██╔══╝  ██║╚██╗██║   ██║
    ██████╔╝       ╚██████╔╝███████╗██║ ╚████║   ██║
    ╚═════╝         ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
    """
    console.print(Align.center(banner), style="bold blue")
    console.print(Align.center("DFIR Automation Agent"), style="white")
    console.print(Align.center(f"v1.0.0 | {datetime.now().strftime('%Y-%m-%d')}"), style="dim")

def create_status_panel(prompt: str, elapsed: float = 0):
    """상태 패널 생성"""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="blue", justify="right")
    table.add_column(style="white")

    table.add_row("Task", prompt[:60] + "..." if len(prompt) > 60 else prompt)
    table.add_row("Status", "Processing...")
    table.add_row("Elapsed", f"{elapsed:.1f}s")

    if step_history:
        table.add_row("", "")
        table.add_row("Steps", "")
        for step in step_history[-5:]:
            table.add_row("", f"[DONE] {step}")

    if current_step:
        table.add_row("", f"[NOW] {current_step}")

    return Panel(
        table,
        title="[bold blue]B-gent Execution[/bold blue]",
        border_style="blue",
        box=box.ROUNDED
    )

def run_with_progress(user_prompt: str, file_paths: list = None, generate_report: bool = False):
    """MongoDB 상태 업데이트만 JSON으로 출력 (나머지 모든 출력 억제)

    Note: MongoDB AGENT_STATES 업데이트는 job_storage.py의 _print_state_json()에서 직접 출력되므로
          별도의 callback 설정 불필요
    """
    original_log_levels = {}

    root_logger = logging.getLogger()
    original_log_levels['root'] = root_logger.level
    root_logger.setLevel(logging.CRITICAL)

    for logger_name in list(logging.root.manager.loggerDict.keys()):
        logger = logging.getLogger(logger_name)
        original_log_levels[logger_name] = logger.level
        logger.setLevel(logging.CRITICAL)

    for logger_name in ['mcp', 'mcp.server', 'mcp.server.lowlevel.server', 'pyghidra_mcp',
                        'src.server', 'FastMCP', 'root']:
        logger = logging.getLogger(logger_name)
        logger.disabled = True
        logger.propagate = False

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    devnull = open(os.devnull, 'w')

    result = None
    try:
        sys.stdout = devnull
        sys.stderr = devnull

        result = run_job(
            user_prompt=user_prompt,
            file_paths=file_paths,
            generate_report_flag=generate_report
        )
    except Exception as e:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        sys.__stdout__.write(f"\nError: {str(e)}\n")
        import traceback
        traceback.print_exc()

        result = {
            "job_id": "error",
            "summary": {"ok": False},
            "error": str(e),
            "traceback": traceback.format_exc()
        }
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        devnull.close()

        for logger_name, level in original_log_levels.items():
            logging.getLogger(logger_name).setLevel(level)

    return result

def display_plans(result: dict):
    """Phase 1 계획 출력 (Phase 2는 실시간 출력되므로 생략)"""
    if WORKFLOW_MODE != "two_stage":
        return

    state = result.get('state', {})

    high_level_tasks = state.get('high_level_tasks', [])
    if high_level_tasks:
        console.print()
        console.print("[bold blue]Phase 1: High-level Planning[/bold blue]")
        console.print(f"[dim]Generated {len(high_level_tasks)} high-level tasks[/dim]")
        console.print()

        for idx, task in enumerate(high_level_tasks, 1):
            task_id = task.get('task_id', 'unknown')
            description = task.get('description', '')
            task_type = task.get('task_type', 'custom')
            dependencies = task.get('dependencies', [])

            console.print(f"{idx}. [bold white][{task_id}][/bold white] {description}")
            console.print(f"   [dim]Type: {task_type} | Dependencies: {', '.join(dependencies) if dependencies else 'None'}[/dim]")

def display_timing(result: dict):
    """각 단계별 소요 시간 출력"""
    if WORKFLOW_MODE != "two_stage":
        return

    state = result.get('state', {})
    completed_tasks = state.get('completed_tasks', [])
    timing = state.get('timing', {})

    if not completed_tasks:
        return

    console.print()
    console.print("[bold blue]Execution Timing[/bold blue]")
    console.print()

    timing_table = Table(box=box.ROUNDED, show_header=True, border_style="blue")
    timing_table.add_column("Task ID", style="blue", width=12)
    timing_table.add_column("Description", style="white", width=40)
    timing_table.add_column("Iterations", justify="right", style="white", width=12)
    timing_table.add_column("Time", justify="right", style="white", width=12)

    total_tasks_time = 0
    task_timings = timing.get('tasks', {})

    for task in completed_tasks:
        task_id = task.get('task_id', 'unknown')
        description = task.get('description', '')[:40]
        react_iterations = task.get('react_iterations', 0)

        task_timing = task_timings.get(task_id, {})
        task_time = task_timing.get('total', 0.0)
        total_tasks_time += task_time

        timing_table.add_row(
            task_id,
            description,
            f"{react_iterations} iter",
            f"{task_time:.2f}s"
        )

    console.print(timing_table)
    console.print()

    high_level_planning_time = timing.get('high_level_planning', 0.0)

    console.print("[bold blue]Phase Breakdown:[/bold blue]")
    console.print(f"  Planning: {high_level_planning_time:.2f}s")

    total_execution = 0.0
    for task_id, task_timing in task_timings.items():
        total_execution += task_timing.get('execution', 0.0)

    console.print(f"  ReAct Execution (all tasks): {total_execution:.2f}s")
    console.print()

    summary = result.get('summary', {})
    if summary:
        total_exec_time = summary.get('execution_time_seconds', 0)
        console.print(f"[bold blue]Total Execution Time:[/bold blue] {total_exec_time:.2f}s")

def display_execution_results(result: dict):
    """각 Task의 MCP 실행 결과 출력"""
    if WORKFLOW_MODE != "two_stage":
        return

    state = result.get('state', {})
    completed_tasks = state.get('completed_tasks', [])

    if not completed_tasks:
        return

    console.print()
    console.print("[bold blue]MCP Execution Results[/bold blue]")
    console.print()

    for task_idx, task in enumerate(completed_tasks, 1):
        task_id = task.get('task_id', 'unknown')
        description = task.get('description', '')
        execution_results = task.get('execution_results', [])

        console.print(f"[bold blue]Task {task_idx}: {description}[/bold blue]")
        console.print()

        if not execution_results:
            console.print("  [dim]No execution results[/dim]")
            console.print()
            continue

        for result_idx, exec_result in enumerate(execution_results, 1):
            success = exec_result.get('success', False)
            action = exec_result.get('action', {})
            tool = action.get('tool', 'unknown')
            operation = action.get('operation', 'unknown')
            reason = action.get('reason', '')
            exec_time = exec_result.get('execution_time_seconds', 0)
            result_data = exec_result.get('result', '')

            status_text = "[OK]" if success else "[FAIL]"

            console.print(f"  {status_text} {tool}.{operation} ({exec_time:.2f}s)")
            if reason:
                console.print(f"     [dim]{reason}[/dim]")

            if result_data:
                result_str = str(result_data)
                if len(result_str) > 2000:
                    result_str = result_str[:2000] + "\n\n...(truncated)"

                console.print()
                console.print(Panel(
                    result_str,
                    title=f"[dim]Result[/dim]",
                    border_style="dim",
                    box=box.MINIMAL,
                    expand=False
                ))
            console.print()

def display_react_results(result: dict):
    """ReAct Agent 결과 표시"""
    state = result.get('state', {})
    observations = state.get('observations', [])
    answer = state.get('answer', '')
    iterations = state.get('iterations', 0)

    console.print()
    console.print("[bold blue]ReAct Agent - Iterative Reasoning Results[/bold blue]")
    console.print()

    for obs in observations:
        iteration = obs.get('iteration', 0)
        thought = obs.get('thought', '')
        action = obs.get('action', {})
        observation = obs.get('observation', '')

        console.print(f"[bold cyan]Iteration {iteration}:[/bold cyan]")
        console.print()

        console.print(f"[yellow]Thinking:[/yellow]")
        console.print(f"  {thought}")
        console.print()

        tool = action.get('tool', 'unknown')
        operation = action.get('operation', 'unknown')
        console.print(f"[green]Action:[/green] {tool}.{operation}")
        console.print()

        obs_preview = observation[:500] if len(observation) > 500 else observation
        console.print(f"[blue]Observation:[/blue]")
        console.print(Panel(
            obs_preview + ("...(truncated)" if len(observation) > 500 else ""),
            border_style="dim",
            box=box.MINIMAL
        ))
        console.print()

    console.print("[bold green]Final Answer:[/bold green]")
    answer_text = answer if answer else "[yellow]No final answer provided - Agent may have reached max iterations without completing analysis[/yellow]"
    console.print(Panel(
        answer_text,
        title="[bold]Analysis Result[/bold]",
        border_style="green" if answer else "yellow",
        box=box.ROUNDED
    ))

    summary = result.get('summary', {})
    console.print()
    console.print(f"[bold blue]Summary:[/bold blue]")
    console.print(f"  Total Iterations: {iterations}")
    console.print(f"  Execution Time: {summary.get('execution_time_seconds', 0):.2f}s")
    console.print()

def display_task_analysis(result: dict):
    """Two-stage 모드에서 각 Task의 분석 결과 출력"""
    if WORKFLOW_MODE != "two_stage":
        return

    state = result.get('state', {})
    completed_tasks = state.get('completed_tasks', [])

    if not completed_tasks:
        return

    console.print()
    console.print("[bold blue]Analysis Results[/bold blue]")
    console.print()

    for task_idx, task in enumerate(completed_tasks, 1):
        description = task.get('description', '')
        react_answer = task.get('react_answer', '')

        if not react_answer:
            continue

        console.print(f"[bold blue]Task {task_idx}: {description}[/bold blue]")
        console.print()

        console.print(react_answer)
        console.print()

def display_result(result: dict):
    """결과 출력"""
    console.print()

    if 'error' in result or 'summary' not in result:
        if 'state' in result:
            display_plans(result)
            display_timing(result)

        error_msg = result.get('error', 'Unknown error occurred')
        console.print()
        console.print(Panel(
            f"[red]Execution failed[/red]\n\n[dim]{error_msg}[/dim]",
            title="[red]Error[/red]",
            border_style="red",
            box=box.ROUNDED
        ))
        console.print()
        return

    state = result.get('state', {})
    if 'observations' in state and 'iterations' in state and WORKFLOW_MODE != "two_stage":
        display_react_results(result)
        return

    display_plans(result)

    display_task_analysis(result)

    display_timing(result)

    summary = result.get('summary', {})
    is_success = summary.get('ok', False)

    status_text = "COMPLETED" if is_success else "PARTIAL"
    status_color = "blue"

    result_table = Table.grid(padding=(0, 2))
    result_table.add_column(style="blue bold", justify="right", width=15)
    result_table.add_column(style="white")

    result_table.add_row("Job ID", f"[dim]{result.get('job_id', 'unknown')[:16]}...[/dim]")
    result_table.add_row("Status", f"[bold]{status_text}[/bold]")
    result_table.add_row("Duration", f"{summary.get('execution_time_seconds', 0):.2f}s")
    result_table.add_row("Steps", f"{summary.get('success_count', 0)} completed, {summary.get('fail_count', 0)} failed")

    console.print()
    console.print(Panel(
        result_table,
        title=f"[bold {status_color}]Execution Result[/bold {status_color}]",
        border_style=status_color,
        box=box.ROUNDED
    ))

    console.print()

def interactive_mode():
    """대화형 터미널 모드"""
    console.print()

    try:
        while True:
            try:
                console.print()
                console.print("[bold blue]>[/bold blue] ", end="")
                prompt = input().strip()

                if prompt.lower() in ['quit', 'exit', 'q']:
                    console.print("\n[dim]Exiting interactive mode...[/dim]")
                    break

                if not prompt:
                    continue

                console.print("[dim]Files (comma로 구분):[/dim] ", end="")
                file_input = input().strip()

                file_paths = None
                if file_input:
                    import os
                    file_paths = []
                    for path in file_input.split(','):
                        path = path.strip()
                        if not path:
                            continue
                        if not os.path.isabs(path):
                            data_path = os.path.join(os.getcwd(), 'data', path)
                            if os.path.exists(data_path):
                                path = data_path
                            else:
                                path = os.path.abspath(path)
                        file_paths.append(path)
                    console.print(f"[dim]→ {len(file_paths)} file(s) provided[/dim]")

                result = run_with_progress(prompt, file_paths=file_paths)

                if not result:
                    console.print(Panel(
                        "[red]No result returned from agent[/red]\n\n"
                        "[yellow]Possible causes:[/yellow]\n"
                        "- LLM response timeout (try faster model)\n"
                        "- Internal error (check logs)\n"
                        "- MCP server connection issue",
                        title="[red]Execution Failed[/red]",
                        border_style="red",
                        box=box.ROUNDED
                    ))
                    continue

                # MongoDB JSON 출력만 사용 - Rich 형식 display 생략
                # display_result(result)

            except EOFError:
                console.print("\n[dim]Exiting interactive mode...[/dim]")
                break
            except KeyboardInterrupt:
                console.print("\n[dim]Exiting interactive mode...[/dim]")
                break
            except Exception as e:
                console.print(Panel(
                    f"[red]Error occurred during execution[/red]\n\n[dim]{str(e)}[/dim]",
                    title="[red]Error[/red]",
                    border_style="red",
                    box=box.ROUNDED
                ))

    finally:
        pass

_cleanup_done = False

def cleanup():
    """프로그램 종료 시 리소스 정리"""
    global _cleanup_done

    if _cleanup_done:
        return

    _cleanup_done = True

    try:
        from agent.mcp_client.singleton import reset_mcp_client
        with SuppressOutput():
            reset_mcp_client()
    except Exception:
        pass

def main():
    """메인 함수"""
    print_banner()
    console.print()

    try:
        interactive_mode()
    except EOFError:
        console.print("\n[dim]Shutting down...[/dim]\n")
    except KeyboardInterrupt:
        console.print("\n[dim]Shutting down...[/dim]\n")
    except Exception as e:
        console.print(Panel(
            f"[red]Unexpected error occurred[/red]\n\n[dim]{str(e)}[/dim]",
            title="[red]Error[/red]",
            border_style="red",
            box=box.ROUNDED
        ))

if __name__ == "__main__":
    console.print()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[dim]Initializing...", total=None)

        try:
            with SuppressOutput():
                from agent.config import get_config
                cfg = get_config()

            progress.update(task, description="[OK] Configuration loaded")
            time.sleep(0.5)

        except Exception as e:
            progress.stop()
            console.print(Panel(
                f"[red]Configuration load failed[/red]\n\n"
                f"[dim]{str(e)}[/dim]\n\n"
                f"[yellow]Please create .env file:[/yellow]\n"
                f"[cyan]cp env.example .env[/cyan]",
                title="[red]Initialization Error[/red]",
                border_style="red",
                box=box.ROUNDED
            ))
            sys.exit(1)

    atexit.register(cleanup)

    try:
        main()
    except Exception as e:
        console.print(Panel(
            f"[red]Unexpected error occurred[/red]\n\n[dim]{str(e)}[/dim]",
            title="[red]Fatal Error[/red]",
            border_style="red",
            box=box.ROUNDED
        ))
        sys.exit(1)
