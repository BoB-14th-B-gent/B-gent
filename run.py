"""
B-gent CLI

DFIR 자동화 에이전트 실행 프로그램
"""
import sys
import os
import atexit
import logging
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
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
from core.agent.router import run_job
console = Console()
current_step = ""
step_history = []

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
    console.print(Align.center(banner), style="bold cyan")
    console.print(Align.center("DFIR Automation Agent"), style="bold white")
    console.print(Align.center(f"v1.0.0 | {datetime.now().strftime('%Y-%m-%d')}"), style="dim")

def create_status_panel(prompt: str, elapsed: float = 0):
    """상태 패널 생성"""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", justify="right")
    table.add_column(style="white")

    table.add_row("Task", prompt[:60] + "..." if len(prompt) > 60 else prompt)
    table.add_row("Status", "[yellow]Processing...[/yellow]")
    table.add_row("Elapsed", f"{elapsed:.1f}s")

    if step_history:
        table.add_row("", "")
        table.add_row("Steps", "")
        for step in step_history[-5:]:  # 최근 5개만 표시
            table.add_row("", f"[green]✓[/green] {step}")

    if current_step:
        table.add_row("", f"[yellow]▸[/yellow] {current_step}")

    return Panel(
        table,
        title="[bold cyan]B-gent Execution[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED
    )

def run_with_progress(user_prompt: str, file_paths: list = None, generate_report: bool = True):
    """진행 상황 표시와 함께 작업 실행"""
    global current_step, step_history
    step_history = []
    current_step = "Initializing agent..."

    start_time = time.time()

    # 실시간 상태 업데이트를 위한 Live 디스플레이
    with Live(create_status_panel(user_prompt, 0), refresh_per_second=4, console=console) as live:
        def update_display():
            elapsed = time.time() - start_time
            live.update(create_status_panel(user_prompt, elapsed))

        # 주기적으로 디스플레이 업데이트
        import threading
        stop_event = threading.Event()

        def periodic_update():
            while not stop_event.is_set():
                update_display()
                time.sleep(0.25)

        update_thread = threading.Thread(target=periodic_update, daemon=True)
        update_thread.start()

        try:
            # 작업 실행 (모든 출력 억제)
            with SuppressOutput():
                result = run_job(
                    user_prompt=user_prompt,
                    file_paths=file_paths,
                    generate_report_flag=generate_report
                )
        finally:
            stop_event.set()
            update_thread.join(timeout=1)
            update_display()  # 마지막 업데이트

    return result

def display_result(result: dict):
    """결과 출력"""
    console.print()

    summary = result.get('summary', {})
    is_success = summary.get('ok', False)

    # 헤더
    status_icon = "✓" if is_success else "⚠"
    status_text = "COMPLETED" if is_success else "PARTIAL"
    status_color = "green" if is_success else "yellow"

    # 결과 테이블
    result_table = Table.grid(padding=(0, 2))
    result_table.add_column(style="cyan bold", justify="right", width=15)
    result_table.add_column(style="white")

    result_table.add_row("Job ID", f"[dim]{result['job_id'][:16]}...[/dim]")
    result_table.add_row("Status", f"[{status_color} bold]{status_icon} {status_text}[/{status_color} bold]")
    result_table.add_row("Duration", f"{summary.get('execution_time_seconds', 0):.2f}s")
    result_table.add_row("Steps", f"{summary.get('success_count', 0)} completed, {summary.get('fail_count', 0)} failed")

    # 리포트 파일
    if 'report' in result and 'saved_files' in result['report']:
        md_file = result['report']['saved_files'].get('markdown_file', '')
        if md_file:
            # 파일명만 추출
            filename = os.path.basename(md_file)
            result_table.add_row("Report", f"[link={md_file}]{filename}[/link]")

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
        border_style="cyan",
        box=box.ROUNDED
    ))

    # 예제 프롬프트 테이블
    examples = Table(box=box.ROUNDED, show_header=True, border_style="dim")
    examples.add_column("Category", style="cyan bold", width=18)
    examples.add_column("Example Prompts", style="white")

    examples.add_row(
        "Metadata",
        "• Show me the list of indices\n• Tell me the schema of winlogbeat-* index"
    )
    examples.add_row(
        "Log Search",
        "• Find cmd.exe execution events in IIS from last 24h\n• Search for Event ID 4624 logs"
    )
    examples.add_row(
        "File Analysis",
        "• Extract suspicious files from disk image\n• Analyze Windows registry hives"
    )

    console.print(examples)
    console.print()

    try:
        while True:
            try:
                # 프롬프트 입력 (한글 입력 지원을 위해 기본 input() 사용)
                console.print()
                console.print("[bold cyan]❯[/bold cyan]: ", end="")
                prompt = input().strip()

                if prompt.lower() in ['quit', 'exit', 'q']:
                    console.print("\n[dim]Exiting interactive mode...[/dim]")
                    break

                if not prompt:
                    continue

                # 작업 실행
                result = run_with_progress(prompt)

                # 결과 표시
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
        from core.agent.mcp_singleton import reset_mcp_client
        with SuppressOutput():
            reset_mcp_client()
    except Exception:
        pass

def main():
    """메인 함수"""
    print_banner()
    console.print()

    # 바로 대화형 모드 실행
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
    # 환경 체크
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
                from core.agent.config import get_config
                cfg = get_config()

            progress.update(task, description="[green]✓ Configuration loaded[/green]")
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

    # 프로그램 종료 시 항상 cleanup 실행
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
