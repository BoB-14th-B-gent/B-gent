"""
B-gent CLI

DFIR 자동화 에이전트 실행 프로그램
"""
import sys
import os
import atexit
import logging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
logging.basicConfig(
    level=logging.WARNING,
    format='%(message)s'
)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("pymongo").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("mcp").setLevel(logging.ERROR)
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
from agent.router import run_job, WORKFLOW_MODE
console = Console()
current_step = ""
step_history = []
phase_timings = {}

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
    """진행 상황 표시와 함께 작업 실행"""
    global current_step, step_history
    step_history = []
    current_step = "Initializing agent..."

    start_time = time.time()

    with Live(create_status_panel(user_prompt, 0), refresh_per_second=4, console=console) as live:
        def update_display():
            elapsed = time.time() - start_time
            live.update(create_status_panel(user_prompt, elapsed))

        import threading
        stop_event = threading.Event()

        def periodic_update():
            while not stop_event.is_set():
                update_display()
                time.sleep(0.25)

        update_thread = threading.Thread(target=periodic_update, daemon=True)
        update_thread.start()

        try:
            with SuppressOutput():
                result = run_job(
                    user_prompt=user_prompt,
                    file_paths=file_paths,
                    generate_report_flag=generate_report
                )
        finally:
            stop_event.set()
            update_thread.join(timeout=1)
            update_display()

    return result

def display_plans(result: dict):
    """Phase 1 및 Phase 2 계획 출력"""
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

    completed_tasks = state.get('completed_tasks', [])
    if completed_tasks:
        console.print()
        console.print("[bold blue]Phase 2: Low-level Planning[/bold blue]")
        console.print(f"[dim]Executed {len(completed_tasks)} tasks with detailed actions[/dim]")
        console.print()

        for task_idx, task in enumerate(completed_tasks, 1):
            task_id = task.get('task_id', 'unknown')
            description = task.get('description', '')
            low_level_plan = task.get('low_level_plan', [])

            console.print(f"{task_idx}. [bold white][{task_id}][/bold white] {description}")

            if low_level_plan:
                for action_idx, action in enumerate(low_level_plan, 1):
                    tool = action.get('tool', 'unknown')
                    operation = action.get('operation', 'unknown')
                    reason = action.get('reason', '')
                    console.print(f"   {action_idx}. {tool}.{operation} - [dim]{reason}[/dim]")
            else:
                console.print(f"   [dim]No low-level actions[/dim]")

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
    timing_table.add_column("Actions", justify="right", style="white", width=10)
    timing_table.add_column("Time", justify="right", style="white", width=12)

    total_tasks_time = 0
    task_timings = timing.get('tasks', {})

    for task in completed_tasks:
        task_id = task.get('task_id', 'unknown')
        description = task.get('description', '')[:40]
        low_level_plan = task.get('low_level_plan', [])
        action_count = len(low_level_plan)

        task_timing = task_timings.get(task_id, {})
        task_time = task_timing.get('total', 0.0)
        total_tasks_time += task_time

        timing_table.add_row(
            task_id,
            description,
            f"{action_count} steps",
            f"{task_time:.2f}s"
        )

    console.print(timing_table)
    console.print()

    high_level_planning_time = timing.get('high_level_planning', 0.0)

    console.print("[bold blue]Phase Breakdown:[/bold blue]")
    console.print(f"  High-level Planning: {high_level_planning_time:.2f}s")

    total_low_level_planning = 0.0
    total_execution = 0.0
    for task_id, task_timing in task_timings.items():
        total_low_level_planning += task_timing.get('low_level_planning', 0.0)
        total_execution += task_timing.get('execution', 0.0)

    console.print(f"  Low-level Planning (all tasks): {total_low_level_planning:.2f}s")
    console.print(f"  MCP Execution (all tasks): {total_execution:.2f}s")
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

    display_plans(result)

    display_execution_results(result)

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
    console.print(Panel(
        Align.center(
            "[bold]Interactive Mode[/bold]\n\n"
            "Enter your analysis prompt freely\n"
            "[dim]Type 'quit', 'exit', or 'q' to exit[/dim]"
        ),
        border_style="blue",
        box=box.ROUNDED
    ))

    examples = Table(box=box.ROUNDED, show_header=True, border_style="blue")
    examples.add_column("Category", style="blue bold", width=18)
    examples.add_column("Example Prompts", style="white")

    examples.add_row(
        "Metadata",
        "- Show me the list of indices\n- Tell me the schema of winlogbeat-* index"
    )
    examples.add_row(
        "Log Search",
        "- Find cmd.exe execution events in IIS from last 24h\n- Search for Event ID 4624 logs"
    )
    examples.add_row(
        "File Analysis",
        "- Extract suspicious files from disk image\n- Analyze Windows registry hives"
    )

    console.print(examples)
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

                result = run_with_progress(prompt)

                display_result(result)

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
        from agent.mcp_singleton import reset_mcp_client
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
