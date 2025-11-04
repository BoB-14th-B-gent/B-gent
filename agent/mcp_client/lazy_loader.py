"""Lazy MCP 클라이언트 모듈

필요한 서버만 지연 초기화하여 성능 최적화
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
from .client import MCPClientManagerSync, MCPServerConfig
from ..config import get_config

_cfg = get_config()
_lazy_clients: Dict[str, MCPClientManagerSync] = {}


def get_mcp_client_for_server(server_name: str) -> MCPClientManagerSync:
    """특정 MCP 서버만 초기화하는 지연 로딩 클라이언트

    Args:
        server_name: 서버 이름 (elastic, velociraptor, sleuthkit 등)

    Returns:
        MCPClientManagerSync: 해당 서버만 연결된 클라이언트

    Example:
        >>> client = get_mcp_client_for_server("elastic")
        >>> result = client.call_tool("elastic", "search_documents", {...})
    """
    global _lazy_clients

    if server_name in _lazy_clients:
        return _lazy_clients[server_name]

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

    print(f"  {server_name} MCP 서버만 초기화 중...")
    client = MCPClientManagerSync([server_config])
    client.initialize()
    print(f"  {server_name} MCP 서버 초기화 완료")

    _lazy_clients[server_name] = client

    return client


def get_mcp_clients_for_servers(server_names: List[str]) -> MCPClientManagerSync:
    """여러 MCP 서버를 한 번에 초기화 (필요한 것만)

    Args:
        server_names: 서버 이름 리스트 (예: ["elastic", "sleuthkit"])

    Returns:
        MCPClientManagerSync: 여러 서버가 연결된 클라이언트
    """
    server_configs = []
    for srv in _cfg.mcp.servers:
        if srv.name in server_names and srv.enabled:
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

    print(f"[✓] {len(server_configs)}개 MCP 서버 초기화 중: {', '.join(server_names)}")
    client = MCPClientManagerSync(server_configs)
    client.initialize()
    print(f"[✓] MCP 서버 초기화 완료")

    return client


def reset_lazy_clients():
    """모든 Lazy 클라이언트 종료 및 리셋"""
    global _lazy_clients

    for server_name, client in _lazy_clients.items():
        try:
            client.close()
        except Exception as e:
            print(f"[!]  {server_name} 종료 실패: {e}")

    _lazy_clients.clear()