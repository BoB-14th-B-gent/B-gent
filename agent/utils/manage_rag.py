"""RAG (ChromaDB) 관리 도구

MCP 도구, 사용자 템플릿(.md), 정책 문서를 관리합니다.
"""
import sys
import os
import json
from pathlib import Path
from collections import defaultdict
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box
from rich.syntax import Syntax
console = Console()
COLLECTION_NAME = "mcp_capabilities"

def get_client():
    """ChromaDB 클라이언트 가져오기"""
    import chromadb
    from agent.config import get_config
    cfg = get_config()
    client = chromadb.PersistentClient(path=cfg.chroma.dir)

    return client

def get_collection():
    """ChromaDB 컬렉션 가져오기"""
    client = get_client()
    coll = client.get_or_create_collection(COLLECTION_NAME)

    return coll

def view_all():
    """모든 도구/문서 보기"""
    coll = get_collection()
    data = coll.get()
    total = coll.count()

    if total == 0:
        console.print("[yellow]⚠️  저장된 데이터가 없습니다.[/yellow]\n")
        console.print("[dim]힌트: '8. MCP 도구 초기 로딩'으로 시작하세요.[/dim]")

        return
    mcp_tools = defaultdict(list)
    user_docs = []

    for idx, (doc_id, meta) in enumerate(zip(data['ids'], data['metadatas'])):
        is_mcp = meta.get('is_mcp', False)

        if is_mcp:
            server = meta.get('server', 'unknown')
            mcp_tools[server].append({
                'id': doc_id,
                'tool_name': meta.get('tool_name', 'N/A'),
                'description': meta.get('description', 'N/A')
            })

        else:
            user_docs.append({
                'id': doc_id,
                'type': meta.get('type', 'document'),
                'title': meta.get('title', 'N/A')
            })
    console.print(f"\n[bold cyan]📊 전체 데이터: {total}개[/bold cyan]\n")

    if mcp_tools:
        console.print(f"[bold green]🔧 MCP 도구: {sum(len(v) for v in mcp_tools.values())}개[/bold green]\n")

        for server, tools in sorted(mcp_tools.items()):
            table = Table(
                title=f"🔧 {server.upper()} ({len(tools)}개)",
                box=box.ROUNDED,
                show_header=True
            )
            table.add_column("ID", style="dim", width=40)
            table.add_column("도구명", style="cyan")
            table.add_column("설명", style="white", overflow="fold")

            for tool in tools:
                table.add_row(
                    tool['id'],
                    tool['tool_name'],
                    tool['description'][:60] + "..." if len(tool['description']) > 60 else tool['description']
                )
            console.print(table)
            console.print()

    if user_docs:
        console.print(f"\n[bold magenta]📝 사용자 문서: {len(user_docs)}개[/bold magenta]\n")
        table = Table(
            title="📝 사용자 추가 문서",
            box=box.ROUNDED,
            show_header=True
        )
        table.add_column("ID", style="dim", width=40)
        table.add_column("타입", style="yellow")
        table.add_column("제목", style="white")

        for doc in user_docs:
            table.add_row(doc['id'], doc['type'], doc['title'])
        console.print(table)
        console.print()

def search_tools():
    """도구/문서 검색"""
    query = Prompt.ask("[bold cyan]검색 쿼리를 입력하세요[/bold cyan]")
    top_k = int(Prompt.ask("[bold cyan]결과 개수[/bold cyan]", default="5"))
    coll = get_collection()
    results = coll.query(query_texts=[query], n_results=top_k)

    if not results or not results['ids'] or len(results['ids'][0]) == 0:
        console.print("[yellow]⚠️  검색 결과가 없습니다.[/yellow]")

        return
    table = Table(title=f"🔍 검색 결과: '{query}'", box=box.ROUNDED, show_header=True)
    table.add_column("순위", style="cyan", width=6)
    table.add_column("ID", style="dim", width=40)
    table.add_column("타입", style="yellow")
    table.add_column("설명", style="white", overflow="fold")

    for idx, (doc_id, meta, doc_text) in enumerate(zip(
        results['ids'][0],
        results['metadatas'][0],
        results['documents'][0]
    ), 1):
        is_mcp = meta.get('is_mcp', False)
        type_str = f"MCP/{meta.get('server', 'N/A')}" if is_mcp else meta.get('type', 'document')
        desc = meta.get('description', '') or meta.get('title', '') or doc_text[:50]
        table.add_row(
            str(idx),
            doc_id,
            type_str,
            desc[:60] + "..." if len(desc) > 60 else desc
        )
    console.print(table)
    console.print()

def view_detail():
    """도구/문서 상세 보기"""
    doc_id = Prompt.ask("[bold cyan]ID를 입력하세요[/bold cyan]")
    coll = get_collection()
    result = coll.get(ids=[doc_id])

    if not result or not result['ids']:
        console.print(f"[red]❌ ID '{doc_id}'를 찾을 수 없습니다.[/red]")

        return
    meta = result['metadatas'][0]
    doc_text = result['documents'][0]
    is_mcp = meta.get('is_mcp', False)
    console.print(Panel(
        f"[bold cyan]ID:[/bold cyan] {doc_id}\n"
        f"[bold cyan]타입:[/bold cyan] {'MCP 도구' if is_mcp else '사용자 문서'}",
        title="📄 문서 상세 정보",
        border_style="cyan"
    ))
    meta_table = Table(box=box.SIMPLE, show_header=False)
    meta_table.add_column("키", style="yellow")
    meta_table.add_column("값", style="white")

    for key, value in meta.items():

        if key == 'input_schema':

            try:
                schema = json.loads(value) if isinstance(value, str) else value
                value_str = json.dumps(schema, indent=2, ensure_ascii=False)

            except:
                value_str = str(value)

        else:
            value_str = str(value)
        meta_table.add_row(key, value_str)
    console.print("\n[bold yellow]메타데이터:[/bold yellow]")
    console.print(meta_table)
    console.print("\n[bold yellow]검색 텍스트:[/bold yellow]")
    console.print(Panel(doc_text, border_style="dim"))
    console.print()

def import_md_file():
    """Markdown 파일 임포트"""
    console.print(Panel(
        "[bold cyan]Markdown 파일을 ChromaDB에 임포트합니다.[/bold cyan]\n\n"
        "템플릿, 정책, 가이드 등을 .md 파일로 작성하여 RAG에 추가할 수 있습니다.\n"
        "[yellow]is_mcp=False로 저장되어 자동 삭제되지 않습니다.[/yellow]",
        title="📥 MD 파일 임포트",
        border_style="green"
    ))
    file_path = Prompt.ask("[bold cyan]MD 파일 경로[/bold cyan]")

    if not os.path.exists(file_path):
        console.print(f"[red]❌ 파일을 찾을 수 없습니다: {file_path}[/red]")

        return

    try:

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

    except Exception as e:
        console.print(f"[red]❌ 파일 읽기 실패: {e}[/red]")

        return
    doc_id = Prompt.ask(
        "[bold cyan]문서 ID[/bold cyan]",
        default=f"user_doc_{Path(file_path).stem}"
    )
    title = Prompt.ask(
        "[bold cyan]문서 제목[/bold cyan]",
        default=Path(file_path).stem
    )
    doc_type = Prompt.ask(
        "[bold cyan]문서 타입[/bold cyan]",
        default="template",
        choices=["template", "policy", "guide", "example", "other"]
    )
    tags = Prompt.ask(
        "[bold cyan]태그 (쉼표로 구분)[/bold cyan]",
        default=""
    )
    coll = get_collection()
    metadata = {
        "type": doc_type,
        "title": title,
        "source_file": file_path,
        "tags": tags,
        "is_mcp": False
    }

    try:
        coll.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[metadata]
        )
        console.print(f"\n[bold green]✅ 임포트 완료![/bold green]")
        console.print(f"   ID: [yellow]{doc_id}[/yellow]")
        console.print(f"   제목: {title}")
        console.print(f"   타입: {doc_type}")
        console.print(f"   크기: {len(content)} 문자\n")

    except Exception as e:
        console.print(f"[red]❌ 임포트 실패: {e}[/red]")

def add_tool():
    """도구 수동 추가"""
    console.print("[bold cyan]도구를 수동으로 추가합니다.[/bold cyan]\n")
    doc_id = Prompt.ask("[bold cyan]문서 ID[/bold cyan]")
    server = Prompt.ask("[bold cyan]서버명[/bold cyan]", default="custom")
    tool_name = Prompt.ask("[bold cyan]도구명[/bold cyan]")
    description = Prompt.ask("[bold cyan]설명[/bold cyan]")
    coll = get_collection()
    text = f"{server} MCP: {description}. Tool: {tool_name}."
    metadata = {
        "tool": "mcp",
        "server": server,
        "tool_name": tool_name,
        "description": description,
        "is_mcp": False
    }
    coll.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])
    console.print(f"\n[green]✅ 도구가 추가되었습니다: {doc_id}[/green]\n")

def delete_by_id():
    """ID로 도구/문서 삭제"""
    doc_id = Prompt.ask("[bold cyan]삭제할 ID를 입력하세요[/bold cyan]")
    coll = get_collection()
    result = coll.get(ids=[doc_id])

    if not result or not result['ids']:
        console.print(f"[yellow]⚠️  ID '{doc_id}'를 찾을 수 없습니다.[/yellow]")

        return
    meta = result['metadatas'][0]
    is_mcp = meta.get('is_mcp', False)
    name = meta.get('tool_name') or meta.get('title', 'N/A')
    console.print(f"\n[yellow]삭제 대상:[/yellow] {doc_id} ({name})")
    console.print(f"[yellow]타입:[/yellow] {'MCP 도구' if is_mcp else '사용자 문서'}\n")

    if Confirm.ask("정말 삭제하시겠습니까?"):
        coll.delete(ids=[doc_id])
        console.print(f"[green]✅ 삭제되었습니다: {doc_id}[/green]\n")

    else:
        console.print("[yellow]취소되었습니다.[/yellow]\n")

def delete_by_server():
    """서버별 MCP 도구 삭제"""
    coll = get_collection()
    data = coll.get(where={"is_mcp": True})

    if not data or not data['ids']:
        console.print("[yellow]⚠️  MCP 도구가 없습니다.[/yellow]")

        return
    servers = set(meta.get('server', 'unknown') for meta in data['metadatas'])
    console.print("\n[bold cyan]사용 가능한 서버:[/bold cyan]")

    for server in sorted(servers):
        count = sum(1 for m in data['metadatas'] if m.get('server') == server)
        console.print(f"  - {server} ({count}개)")
    server = Prompt.ask("\n[bold cyan]삭제할 서버명을 입력하세요[/bold cyan]")
    target_ids = [
        doc_id for doc_id, meta in zip(data['ids'], data['metadatas'])

        if meta.get('server') == server
    ]

    if not target_ids:
        console.print(f"[yellow]⚠️  서버 '{server}'의 도구가 없습니다.[/yellow]")

        return
    console.print(f"\n[yellow]삭제 대상:[/yellow] {server} 서버의 {len(target_ids)}개 도구\n")

    if Confirm.ask("정말 삭제하시겠습니까?"):
        coll.delete(ids=target_ids)
        console.print(f"[green]✅ {len(target_ids)}개 도구가 삭제되었습니다.[/green]\n")

    else:
        console.print("[yellow]취소되었습니다.[/yellow]\n")

def delete_all():
    """전체 삭제"""
    coll = get_collection()
    total = coll.count()

    if total == 0:
        console.print("[yellow]⚠️  삭제할 데이터가 없습니다.[/yellow]")

        return
    console.print(f"\n[red bold]⚠️  경고: 모든 데이터({total}개)를 삭제합니다![/red bold]\n")

    if not Confirm.ask("정말 모든 데이터를 삭제하시겠습니까?"):
        console.print("[yellow]취소되었습니다.[/yellow]\n")

        return

    if not Confirm.ask("[red]한번 더 확인: 정말로 삭제하시겠습니까?[/red]"):
        console.print("[yellow]취소되었습니다.[/yellow]\n")

        return
    client = get_client()
    client.delete_collection(COLLECTION_NAME)
    client.create_collection(COLLECTION_NAME)
    console.print(f"[green]✅ 모든 데이터가 삭제되었습니다.[/green]\n")

def load_mcp_tools():
    """MCP 서버에서 도구 초기 로딩 (확정 저장)"""
    console.print(Panel(
        "[bold cyan]MCP 서버에서 도구 정보를 가져와 확정 저장합니다.[/bold cyan]\n\n"
        "한번 저장하면 이후로는 MCP 서버 연결 없이 ChromaDB에서 바로 사용합니다.\n"
        "[yellow]주의: 기존 MCP 도구(is_mcp=True)는 모두 삭제됩니다.[/yellow]",
        title="🔄 MCP 도구 초기 로딩",
        border_style="green"
    ))
    coll = get_collection()
    existing = coll.get(where={"is_mcp": True})
    existing_count = len(existing['ids']) if existing and existing['ids'] else 0

    if existing_count > 0:
        console.print(f"\n[yellow]⚠️  기존 MCP 도구 {existing_count}개가 있습니다.[/yellow]")

        if not Confirm.ask("기존 MCP 도구를 삭제하고 새로 로딩하시겠습니까?"):
            console.print("[yellow]취소되었습니다.[/yellow]\n")

            return
        coll.delete(ids=existing['ids'])
        console.print(f"[green]✅ 기존 MCP 도구 {existing_count}개 삭제 완료[/green]")
    console.print("\n[cyan]⏳ MCP 서버 연결 중...[/cyan]")

    try:
        from agent.mcp_client.singleton import get_mcp_client
        client = get_mcp_client()
        mcp_tools = client.get_all_tools()
        console.print(f"[green]✅ MCP 서버에서 {len(mcp_tools)}개 도구 발견[/green]\n")
        docs_to_add = []

        for tool in mcp_tools:
            doc_id = f"mcp_{tool['server']}_{tool['name']}"
            schema_str = json.dumps(tool.get('input_schema', {}), ensure_ascii=False)
            text = f"{tool['server']} MCP: {tool['description']}. Tool: {tool['name']}. Schema: {schema_str}"
            docs_to_add.append({
                "id": doc_id,
                "text": text,
                "meta": {
                    "tool": "mcp",
                    "server": tool["server"],
                    "tool_name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": schema_str,
                    "is_mcp": True
                }
            })

        if docs_to_add:
            coll.upsert(
                ids=[d["id"] for d in docs_to_add],
                documents=[d["text"] for d in docs_to_add],
                metadatas=[d["meta"] for d in docs_to_add]
            )
            console.print(f"[bold green]✅ {len(docs_to_add)}개 MCP 도구가 ChromaDB에 저장되었습니다![/bold green]\n")
            console.print("[dim]이제 MCP 서버 연결 없이 빠르게 사용할 수 있습니다.[/dim]\n")
            servers = defaultdict(int)

            for tool in mcp_tools:
                servers[tool['server']] += 1
            console.print("[bold]서버별 도구 개수:[/bold]")

            for server, count in sorted(servers.items()):
                console.print(f"  • {server}: {count}개")
            console.print()

    except Exception as e:
        console.print(f"[red]❌ MCP 도구 로딩 실패: {e}[/red]")
        import traceback
        traceback.print_exc()

def export_data():
    """JSON으로 내보내기"""
    coll = get_collection()
    data = coll.get()
    total = coll.count()

    if total == 0:
        console.print("[yellow]⚠️  내보낼 데이터가 없습니다.[/yellow]")

        return
    output_file = Prompt.ask(
        "[bold cyan]저장할 파일명[/bold cyan]",
        default="rag_backup.json"
    )
    export_data = {
        "total": total,
        "collection": COLLECTION_NAME,
        "items": []
    }

    for doc_id, doc_text, meta in zip(data['ids'], data['documents'], data['metadatas']):
        export_data["items"].append({
            "id": doc_id,
            "document": doc_text,
            "metadata": meta
        })

    try:

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        console.print(f"\n[green]✅ 내보내기 완료: {output_file}[/green]")
        console.print(f"   총 {total}개 항목\n")

    except Exception as e:
        console.print(f"[red]❌ 내보내기 실패: {e}[/red]")

def print_banner():
    """배너 출력"""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║        🗄️  RAG (ChromaDB) 관리 도구                      ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")

def main():
    """메인 함수"""
    print_banner()

    menu = Table(box=box.ROUNDED, show_header=False, title="📋 메뉴", title_style="bold cyan")
    menu.add_column("번호", style="cyan", width=8)
    menu.add_column("항목", style="white")

    menu.add_row("1", "📊 모든 도구/문서 보기")
    menu.add_row("2", "🔍 도구/문서 검색")
    menu.add_row("3", "📄 도구/문서 상세 보기")
    menu.add_row("4", "📥 MD 파일 임포트")
    menu.add_row("5", "➕ 도구 수동 추가")
    menu.add_row("6", "🗑️  도구/문서 삭제 (ID)")
    menu.add_row("7", "🗑️  서버별 MCP 도구 삭제")
    menu.add_row("8", "🔄 MCP 도구 초기 로딩 (확정)")
    menu.add_row("9", "🗑️  전체 삭제")
    menu.add_row("10", "💾 JSON으로 내보내기")
    menu.add_row("0", "🚪 종료")

    console.print(menu)

    while True:
        try:
            choice = Prompt.ask(
                "\n[bold cyan]선택[/bold cyan]",
                choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
                default="1"
            )

            console.print()

            if choice == '1':
                view_all()
            elif choice == '2':
                search_tools()
            elif choice == '3':
                view_detail()
            elif choice == '4':
                import_md_file()
            elif choice == '5':
                add_tool()
            elif choice == '6':
                delete_by_id()
            elif choice == '7':
                delete_by_server()
            elif choice == '8':
                load_mcp_tools()
            elif choice == '9':
                delete_all()
            elif choice == '10':
                export_data()
            elif choice == '0':
                console.print("[yellow]👋 종료합니다.[/yellow]")
                break

        except EOFError:
            console.print("\n[yellow]👋 종료합니다.[/yellow]")
            break
        except KeyboardInterrupt:
            console.print("\n[yellow]👋 종료합니다.[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]❌ 오류: {e}[/red]")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"\n[red]❌ 예상치 못한 오류: {e}[/red]")
        sys.exit(1)
    finally:
        try:
            from agent.mcp_client.singleton import reset_mcp_client
            reset_mcp_client()
        except:
            pass
