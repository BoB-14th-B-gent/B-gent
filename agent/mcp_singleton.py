"""MCP 클라이언트 전역 싱글톤 모듈

여러 모듈에서 동일한 MCP 연결 재사용을 위한 전역 싱글톤 패턴 MCP 클라이언트 관리
"""
from __future__ import annotations
from typing import Optional
from .mcp_client import MCPClientManagerSync, MCPServerConfig
from .config import get_config
_cfg = get_config()
_mcp_client: Optional[MCPClientManagerSync] = None

def get_mcp_client() -> MCPClientManagerSync:
    """MCP 클라이언트 전역 싱글톤 반환

    첫 호출 시 MCP 클라이언트 초기화, 이후 호출에서는 캐시된 인스턴스 반환
    여러 모듈에서 동일한 MCP 연결 재사용으로 오버헤드 최소화

    로직:
        1. 전역 변수 _mcp_client가 None인지 확인
        2. None이면:
           a. 설정에서 활성화된 MCP 서버 목록 가져오기
           b. MCPClientManagerSync 인스턴스 생성
           c. 초기화 (모든 MCP 서버 연결)
           d. 전역 변수에 저장
        3. 캐시된 클라이언트 반환

    Returns:
        MCPClientManagerSync: 초기화된 MCP 클라이언트 인스턴스

    Raises:
        RuntimeError: 활성화된 MCP 서버가 없는 경우

    Example:
        >>> from agent.mcp_singleton import get_mcp_client
        >>> client = get_mcp_client()
        >>> tools = client.get_all_tools()
        >>> result = client.call_tool("elastic", "search_documents", {...})
    """
    global _mcp_client

    if _mcp_client is None:
        server_configs = [
            MCPServerConfig(
                name=srv.name,
                url=srv.url,
                command=srv.command,
                args=srv.args,
                env=srv.env,
                headers=srv.headers
            )

            for srv in _cfg.mcp.servers

            if srv.enabled
        ]

        if not server_configs:
            raise RuntimeError("활성화된 MCP 서버가 없습니다.")
        print("🔌 전역 MCP 클라이언트 초기화 중...")
        _mcp_client = MCPClientManagerSync(server_configs)
        _mcp_client.initialize()
        print("✓ 전역 MCP 클라이언트 초기화 완료")

    return _mcp_client

def reset_mcp_client():
    """MCP 클라이언트 리셋 (테스트용)

    전역 싱글톤 종료 및 None으로 리셋
    다음 get_mcp_client() 호출 시 새로운 인스턴스 생성

    Note:
        주로 테스트 코드에서 사용
        운영 환경에서는 사용 권장하지 않음
    """
    global _mcp_client

    if _mcp_client is not None:
        _mcp_client.close()
        _mcp_client = None

