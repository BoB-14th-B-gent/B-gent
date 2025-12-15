"""Lazy MCP 클라이언트 모듈

필요한 서버만 지연 초기화하여 성능 최적화
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, Any, List, Optional
from .client import MCPClientManagerSync, MCPServerConfig
from ..config import get_config
from ..utils.debug import debug_print, debug_write

_cfg = get_config()
_lazy_clients: Dict[str, MCPClientManagerSync] = {}

_connection_failure_cache: Dict[str, tuple] = {}
_RETRY_COOLDOWN_SECONDS = 300  # 5분 후 재시도
_MAX_FAILURE_COUNT = 3  # 최대 실패 횟수 (이후 해당 세션에서 영구 스킵)


def _should_skip_server(server_name: str) -> bool:
    """연결 실패 캐시를 확인하여 서버 연결을 건너뛸지 결정

    Args:
        server_name: MCP 서버 이름

    Returns:
        bool: True면 연결 시도 건너뛰기
    """
    if server_name not in _connection_failure_cache:
        return False

    last_failure_time, failure_count = _connection_failure_cache[server_name]

    if failure_count >= _MAX_FAILURE_COUNT:
        return True

    elapsed = (datetime.now() - last_failure_time).total_seconds()
    if elapsed < _RETRY_COOLDOWN_SECONDS:
        return True

    return False


def _record_connection_failure(server_name: str):
    """연결 실패 기록

    Args:
        server_name: 실패한 MCP 서버 이름
    """
    if server_name in _connection_failure_cache:
        _, failure_count = _connection_failure_cache[server_name]
        _connection_failure_cache[server_name] = (datetime.now(), failure_count + 1)
    else:
        _connection_failure_cache[server_name] = (datetime.now(), 1)

    failure_count = _connection_failure_cache[server_name][1]
    if failure_count >= _MAX_FAILURE_COUNT:
        debug_write(f"│ [MCP] Server '{server_name}' reached max failures ({_MAX_FAILURE_COUNT}), skipping for this session\n")
    else:
        debug_write(f"│ [MCP] Server '{server_name}' connection failed (attempt {failure_count}/{_MAX_FAILURE_COUNT})\n")


def _clear_connection_failure(server_name: str):
    """연결 성공 시 실패 기록 제거

    Args:
        server_name: 성공한 MCP 서버 이름
    """
    if server_name in _connection_failure_cache:
        del _connection_failure_cache[server_name]


def get_mcp_client_for_server(server_name: str) -> MCPClientManagerSync:
    """특정 MCP 서버만 초기화하는 지연 로딩 클라이언트

    Args:
        server_name: 서버 이름 (elastic, velociraptor, sleuthkit 등)

    Returns:
        MCPClientManagerSync: 해당 서버만 연결된 클라이언트

    Raises:
        RuntimeError: 서버가 비활성화되었거나 연결 실패 캐시에 있는 경우

    Example:
        >>> client = get_mcp_client_for_server("elastic")
        >>> result = client.call_tool("elastic", "search_documents", {...})
    """
    global _lazy_clients

    if server_name in _lazy_clients:
        return _lazy_clients[server_name]

    if _should_skip_server(server_name):
        raise RuntimeError(f"MCP 서버 '{server_name}' 연결이 이전에 실패했습니다. 잠시 후 다시 시도하세요.")

    server_config = None
    for srv in _cfg.mcp.servers:
        if srv.name == server_name and srv.enabled:
            server_config = MCPServerConfig(
                name=srv.name,
                url=srv.url,
                command=srv.command,
                args=srv.args,
                env=srv.env,
                headers=srv.headers
            )
            break

    if not server_config:
        raise RuntimeError(f"MCP 서버 '{server_name}'이(가) 활성화되지 않았거나 존재하지 않습니다.")

    try:
        client = MCPClientManagerSync([server_config])
        client.initialize()

        _lazy_clients[server_name] = client
        _clear_connection_failure(server_name)  # 성공 시 실패 기록 제거

        return client

    except Exception as e:
        _record_connection_failure(server_name)
        raise RuntimeError(f"MCP 서버 '{server_name}' 초기화 실패: {e}")


def get_mcp_clients_for_servers(server_names: List[str]) -> MCPClientManagerSync:
    """여러 MCP 서버를 한 번에 초기화 (필요한 것만)

    연결 실패 캐시에 있는 서버는 건너뛰고 나머지만 초기화합니다.

    Args:
        server_names: 서버 이름 리스트 (예: ["elastic", "sleuthkit"])

    Returns:
        MCPClientManagerSync: 여러 서버가 연결된 클라이언트

    Raises:
        RuntimeError: 모든 요청 서버가 비활성화되었거나 실패 캐시에 있는 경우
    """
    valid_server_names = [name for name in server_names if not _should_skip_server(name)]
    skipped_servers = [name for name in server_names if _should_skip_server(name)]

    if skipped_servers:
        debug_write(f"│ [MCP] Skipping previously failed servers: {', '.join(skipped_servers)}\n")

    server_configs = []
    for srv in _cfg.mcp.servers:
        if srv.name in valid_server_names and srv.enabled:
            server_configs.append(MCPServerConfig(
                name=srv.name,
                url=srv.url,
                command=srv.command,
                args=srv.args,
                env=srv.env,
                headers=srv.headers
            ))

    if not server_configs:
        raise RuntimeError(f"요청한 MCP 서버가 활성화되지 않았습니다: {server_names}")

    try:
        client = MCPClientManagerSync(server_configs)
        client.initialize()

        for srv in server_configs:
            _clear_connection_failure(srv.name)

        return client

    except Exception as e:
        for name in valid_server_names:
            _record_connection_failure(name)
        raise RuntimeError(f"MCP 서버 초기화 실패: {e}")


def reset_lazy_clients():
    """모든 Lazy 클라이언트 종료 및 리셋"""
    global _lazy_clients

    for server_name, client in _lazy_clients.items():
        try:
            client.close()
        except Exception as e:
            debug_print(f"[!]  {server_name} 종료 실패: {e}")

    _lazy_clients.clear()