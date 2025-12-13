"""MCP (Model Context Protocol) 클라이언트 매니저 모듈

여러 MCP 서버들과의 연결 관리, 도구 목록 자동 수집,
도구 호출 통합 인터페이스 제공
stdio 및 HTTP/SSE/StreamableHTTP 프로토콜 지원
"""
from __future__ import annotations
import asyncio
import json
import sys
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from contextlib import asynccontextmanager, AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
logging.basicConfig(level=logging.WARNING)
mcp_logger = logging.getLogger("mcp")
mcp_logger.setLevel(logging.INFO)

@dataclass

class MCPServerConfig:
    """MCP 서버 설정

    Attributes:
        name: 서버 고유 식별자 (예: elastic, velociraptor)
        url: HTTP/SSE URL (HTTP 모드)
        command: stdio 실행 명령 (stdio 모드)
        args: stdio 명령 인자
        env: 환경 변수
        headers: HTTP 헤더 (Authorization 등)
    """
    name: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    headers: Optional[Dict[str, str]] = None

class MCPClientManager:
    """여러 MCP 서버를 관리하는 비동기 클라이언트

    stdio, HTTP/SSE/StreamableHTTP 프로토콜 지원,
    여러 MCP 서버와 동시에 연결하고 도구 호출 가능
    """

    def __init__(self, server_configs: List[MCPServerConfig]):
        self.configs = {cfg.name: cfg for cfg in server_configs}
        self.sessions: Dict[str, ClientSession] = {}
        self.tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._initialized = False
        self._exit_stack = AsyncExitStack()

    async def initialize(self):
        """모든 MCP 서버 연결 및 도구 목록 수집"""
        if self._initialized:

            return

        for name, config in self.configs.items():

            try:
                session = await asyncio.wait_for(
                    self._connect_server(config),
                    timeout=120.0
                )
                self.sessions[name] = session
                tools_result = await asyncio.wait_for(
                    session.list_tools(),
                    timeout=60.0
                )
                self.tools_cache[name] = [
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema,
                        "server": name
                    }

                    for tool in tools_result.tools
                ]

            except asyncio.TimeoutError:
                print(f"MCP 서버 연결 타임아웃: {name} (응답 없음, 건너뜀)")
                self.tools_cache[name] = []

            except Exception as e:
                import traceback
                print(f"MCP 서버 연결 실패: {name} - {e}")
                print(f"  상세 오류:\n{traceback.format_exc()}")
                self.tools_cache[name] = []
        self._initialized = True

    async def _connect_server(self, config: MCPServerConfig) -> ClientSession:
        """개별 MCP 서버 연결 (stdio 또는 http)"""
        import os
        verbose = os.getenv("MCP_DEBUG") == "1"

        if verbose:
            print(f"DEBUG [{config.name}]:")
            if config.url:
                print(f"   Mode: HTTP")
                print(f"   URL: {config.url}")
            else:
                print(f"   Mode: stdio")
                print(f"   Command: {config.command}")
                print(f"   Args: {config.args}")
                print(f"   Env: {config.env}")

        try:

            if config.url:

                if "/mcp" in config.url or "streamable" in config.url.lower():
                    headers = {
                        "Accept": "application/json, text/event-stream",
                        "Content-Type": "application/json"
                    }

                    if config.headers:
                        headers.update(config.headers)
                    if verbose:
                        print(f"  HTTP 헤더: {list(headers.keys())}")
                    client_context = streamablehttp_client(config.url, headers=headers)
                    result = await self._exit_stack.enter_async_context(client_context)
                    read, write = result[0], result[1]
                else:
                    headers = config.headers or {}
                    client_context = sse_client(config.url, headers=headers)
                    read, write = await self._exit_stack.enter_async_context(client_context)

            elif config.command:
                if verbose:
                    print(f"  stdio 클라이언트 생성 중...")
                import os
                env_merged = os.environ.copy()
                env_merged.pop("VIRTUAL_ENV", None)

                if config.env:
                    env_merged.update(config.env)
                env_merged["PYTHONUNBUFFERED"] = "1"
                # Windows cp949 인코딩 문제 해결을 위한 UTF-8 강제 설정
                env_merged["PYTHONIOENCODING"] = "utf-8"
                env_merged["PYTHONUTF8"] = "1"

                # # debug mode
                # if os.getenv("MCP_DEBUG") != "1":
                #     env_merged["LOGLEVEL"] = "ERROR"
                #     env_merged["LOG_LEVEL"] = "ERROR"
                #     env_merged["PYTHONWARNINGS"] = "ignore"

                params = StdioServerParameters(
                    command=config.command,
                    args=config.args or [],
                    env=env_merged
                )
                errlog = sys.stderr if verbose else open(os.devnull, 'w')
                client_context = stdio_client(params, errlog=errlog)
                read, write = await self._exit_stack.enter_async_context(client_context)
                if verbose:
                    print(f"  [OK] stdio 스트림 연결 완료")

            else:
                raise ValueError(f"MCP 서버 설정에 url 또는 command가 필요합니다: {config.name}")
            if verbose:
                print(f"  ClientSession 생성 중...")
            session = await self._exit_stack.enter_async_context(ClientSession(read, write))
            init_timeout = 60.0 if config.command else 30.0

            try:
                import time
                start_time = time.time()
                if verbose:
                    # print(f"  initialize() 호출 중... (서버: {config.name})")
                    pass
                result = await asyncio.wait_for(session.initialize(), timeout=init_timeout)
                elapsed = time.time() - start_time
                if verbose:
                    # print(f"  세션 초기화 완료 (소요 시간: {elapsed:.2f}초)")
                    pass
                    print(f"  서버 정보: {result.serverInfo.name} v{result.serverInfo.version}")
                    if result.capabilities.tools:
                        print(f"  도구 기능 지원됨")

            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                # print(f"  초기화 타임아웃 ({elapsed:.2f}/{init_timeout}초)")
                pass
                raise

            except Exception as e:
                # print(f"  초기화 중 예외 발생: {type(e).__name__}: {e}")
                pass
                raise

            return session

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"상세 에러:\n{error_details}")
            raise RuntimeError(f"MCP 서버 연결 실패 ({config.name}): {e}")

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """모든 MCP 서버의 도구 목록 반환"""
        all_tools = []

        for server_name, tools in self.tools_cache.items():
            all_tools.extend(tools)

        return all_tools

    def get_tools_by_server(self, server_name: str) -> List[Dict[str, Any]]:
        """특정 서버의 도구 목록만 반환"""
        return self.tools_cache.get(server_name, [])

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        """MCP 도구 호출 (타임아웃 지원)

        Args:
            server_name: 서버 이름
            tool_name: 도구 이름
            arguments: 도구 인자
            timeout: 타임아웃 (초), None이면 무제한

        Returns:
            Dict[str, Any]: 실행 결과
        """
        if server_name not in self.sessions:
            raise ValueError(f"MCP 서버가 연결되지 않음: {server_name}")
        session = self.sessions[server_name]

        try:
            if timeout:
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments=arguments),
                    timeout=timeout
                )
            else:
                result = await session.call_tool(tool_name, arguments=arguments)
            content_parts = []

            for item in result.content:

                if hasattr(item, 'text') and item.text is not None:
                    content_parts.append(item.text)

                elif hasattr(item, 'data') and item.data is not None:
                    content_parts.append(json.dumps(item.data))
            result_text = "\n".join(content_parts) if content_parts else str(result.content)
            success = True
            error_message = None

            try:
                result_json = json.loads(result_text)

                if isinstance(result_json, dict) and "ok" in result_json:
                    success = result_json.get("ok", False)
                    if not success:
                        error_message = result_json.get("error", result_json.get("message", ""))
                        if not error_message:
                            error_message = f"MCP 도구 실행 실패 (ok=False, 응답: {str(result_json)[:300]})"

                elif result.isError if hasattr(result, 'isError') else False:
                    success = False
                    if isinstance(result_json, dict):
                        error_message = result_json.get("error", result_json.get("message", ""))
                        if not error_message:
                            error_message = f"MCP 도구 실행 중 에러 발생 (응답: {str(result_json)[:300]})"
                    else:
                        error_message = f"MCP 도구 실행 중 에러 발생 (응답: {str(result_json)[:300]})"

            except (json.JSONDecodeError, ValueError):
                if result.isError if hasattr(result, 'isError') else False:
                    success = False
                    error_message = f"MCP 응답 파싱 실패 (JSON 아님, isError=True): {result_text[:200]}"

            response = {
                "success": success,
                "is_error": result.isError if hasattr(result, 'isError') else False
            }

            if success:
                response["result"] = result_text
            else:
                response["error"] = error_message or f"알 수 없는 오류 (응답: {result_text[:200]})"
                response["result"] = result_text

            return response

        except Exception as e:

            return {
                "success": False,
                "error": str(e),
                "is_error": True
            }

    async def close(self):
        """모든 MCP 서버 연결 종료"""
        try:
            await self._exit_stack.aclose()
        except RuntimeError as e:
            # anyio의 cancel scope 관련 에러는 무시 (다른 태스크에서 종료 시도 시 발생)
            # 프로세스 종료 직전에 발생하므로 기능적 영향 없음
            if "cancel scope" in str(e).lower():
                pass
            else:
                print(f"[FAIL] MCP 서버 종료 중 오류: {e}")
        except Exception as e:
            print(f"[FAIL] MCP 서버 종료 중 오류: {e}")
        self.sessions.clear()
        self._initialized = False

class MCPClientManagerSync:
    """동기 방식 래퍼 (기존 코드 호환용)"""

    def __init__(self, server_configs: List[MCPServerConfig]):
        import threading
        self.manager = MCPClientManager(server_configs)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread_id: Optional[int] = None  # 이벤트 루프가 생성된 스레드 ID
        self._initialized = False

    def _get_or_create_loop(self) -> asyncio.AbstractEventLoop:
        """이벤트 루프 가져오기 또는 생성

        중요: asyncio 이벤트 루프는 스레드 바운드입니다.
        다른 스레드에서 호출되면 새 이벤트 루프를 생성해야 합니다.
        (ThreadPoolExecutor에서 호출 시 데드락 방지)
        """
        import threading
        current_thread_id = threading.current_thread().ident

        # 기존 루프가 있고, 같은 스레드에서 호출된 경우에만 재사용
        if (self._loop is not None
            and not self._loop.is_closed()
            and self._loop_thread_id == current_thread_id):
            return self._loop

        # 다른 스레드에서 호출되었거나 루프가 없는 경우 새로 생성
        try:
            running_loop = asyncio.get_running_loop()
            print("[!]  Warning: 실행 중인 이벤트 루프가 감지되었습니다. 새 루프를 생성합니다.")
        except RuntimeError:
            pass

        try:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)

            # 메인 스레드인 경우에만 캐시 (다른 스레드는 일회성 루프 사용)
            if threading.current_thread() is threading.main_thread():
                self._loop = new_loop
                self._loop_thread_id = current_thread_id

            return new_loop

        except Exception as e:
            print(f"[!]  이벤트 루프 생성 실패, 기본 루프 사용: {e}")

            try:
                return asyncio.get_event_loop()
            except RuntimeError:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                return new_loop

    def initialize(self):
        """동기 방식 초기화"""
        if self._initialized:

            return

        try:
            loop = self._get_or_create_loop()
            loop.run_until_complete(self.manager.initialize())
            self._initialized = True

        except Exception as e:
            raise RuntimeError(f"MCP 클라이언트 초기화 실패: {e}")

    def get_all_tools(self) -> List[Dict[str, Any]]:

        if not self._initialized:
            self.initialize()

        return self.manager.get_all_tools()

    def get_tools_by_server(self, server_name: str) -> List[Dict[str, Any]]:

        if not self._initialized:
            self.initialize()

        return self.manager.get_tools_by_server(server_name)

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        """동기 방식 도구 호출 (타임아웃 지원)

        Args:
            server_name: 서버 이름
            tool_name: 도구 이름
            arguments: 도구 인자
            timeout: 타임아웃 (초), None이면 무제한

        Returns:
            Dict[str, Any]: 실행 결과
        """
        if not self._initialized:
            self.initialize()

        try:
            loop = self._get_or_create_loop()

            return loop.run_until_complete(
                self.manager.call_tool(server_name, tool_name, arguments, timeout=timeout)
            )

        except Exception as e:
            import traceback

            return {
                "success": False,
                "error": f"MCP 도구 호출 실패: {e}",
                "traceback": traceback.format_exc(),
                "is_error": True
            }

    def close(self):
        """동기 방식 종료"""
        if not self._initialized:

            return

        try:

            if self._loop and not self._loop.is_closed():
                self._loop.run_until_complete(self.manager.close())
                self._loop.close()
                self._loop = None
            self._initialized = False

        except Exception as e:
            print(f"[!]  MCP 클라이언트 종료 중 오류: {e}")

    def __enter__(self):
        self.initialize()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        """소멸자: 객체가 삭제될 때 자동으로 종료"""
        try:

            if self._initialized and self._loop and not self._loop.is_closed():

                try:
                    asyncio.get_running_loop()

                except RuntimeError:
                    self.close()

        except Exception:
            pass

