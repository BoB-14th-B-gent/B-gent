"""환경 설정 모듈

B-gent 에이전트의 모든 환경 설정 관리
.env 파일에서 환경 변수 로드 및 각 외부 시스템의 연결 정보 제공
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

def _load_env_file():
    """python-dotenv가 없을 때 수동으로 .env 파일 로드

    프로젝트 루트의 .env 파일 파싱 및 환경 변수 설정
    이미 환경 변수에 설정된 값은 덮어쓰지 않음

    로직:
        1. 프로젝트 루트의 .env 파일 경로 계산
        2. 파일이 존재하면 한 줄씩 읽기
        3. 주석(#)이 아니고 '='를 포함한 줄만 처리
        4. key=value 형식으로 파싱
        5. 환경 변수에 없는 값만 설정
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')

    if os.path.exists(env_path):

        with open(env_path, 'r', encoding='utf-8') as f:

            for line in f:
                line = line.strip()

                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    if key not in os.environ:
                        os.environ[key] = value

try:
    from dotenv import load_dotenv
    load_dotenv()

except ImportError:
    _load_env_file()

@dataclass

class MongoConfig:
    """MongoDB 연결 설정

    Attributes:
        uri: MongoDB 연결 URI (예: mongodb://user:pass@localhost:27017)
        db: 사용할 데이터베이스 이름
    """
    uri: str = "mongodb://localhost:27017"
    db: str = "bgent"

@dataclass

class ChromaConfig:
    """ChromaDB 설정

    Attributes:
        dir: ChromaDB 데이터 저장 디렉터리 경로
    """
    dir: str = "./data/chroma"

@dataclass

class LLMConfig:
    """LLM 서버 연결 설정

    Attributes:
        base_url: LLM API 서버 기본 URL
        model: 사용할 모델 이름 (예: llama-3.1-8b-instruct)
        api_key: API 인증 키 (선택)
        api_kind: API 종류 (openai 또는 ollama)
        verify_ssl: SSL 인증서 검증 여부
        context_size: 컨텍스트 윈도우 크기 (토큰 수)
    """
    base_url: str
    model: str
    api_key: Optional[str] = None
    api_kind: str = "openai"
    verify_ssl: bool = True
    context_size: int = 4096

@dataclass

class ElasticConfig:
    """Elasticsearch 연결 설정

    Attributes:
        base_url: Elasticsearch 서버 기본 URL
        user: 인증 사용자명
        password: 인증 비밀번호
        default_indices: 기본 검색 인덱스 목록
        time_field: 타임스탬프 필드 이름
        verify_ssl: SSL 인증서 검증 여부
    """
    base_url: str
    user: str
    password: str
    default_indices: list[str]
    time_field: str = "@timestamp"
    verify_ssl: bool = True

@dataclass

class VelociraptorConfig:
    """Velociraptor 서버 연결 설정

    Attributes:
        base_url: Velociraptor API 서버 기본 URL
        api_token: API 인증 토큰
        verify_ssl: SSL 인증서 검증 여부
    """
    base_url: str
    api_token: str
    verify_ssl: bool = True

@dataclass

class SleuthKitConfig:
    """SleuthKit 도구 설정

    Attributes:
        bin_dir: SleuthKit 바이너리 디렉터리 경로 (fls, icat 등)
    """
    bin_dir: str = "/usr/bin"

@dataclass

class MCPServerConfigItem:
    """개별 MCP 서버 설정

    Attributes:
        name: 서버 고유 식별자 (예: elastic, velociraptor)
        url: HTTP/SSE URL (HTTP 모드인 경우)
        command: stdio 실행 명령 (stdio 모드인 경우)
        args: stdio 명령 인자
        env: 환경 변수 딕셔너리
        headers: HTTP 헤더 (Authorization 등)
        enabled: 서버 활성화 여부
    """
    name: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    headers: Optional[dict[str, str]] = None
    enabled: bool = True

@dataclass

class MCPConfig:
    """MCP 서버들 설정

    Attributes:
        enabled: MCP 기능 사용 여부
        servers: MCP 서버 설정 목록
    """
    enabled: bool = False
    servers: list[MCPServerConfigItem] = None

    def __post_init__(self):
        """dataclass 초기화 후 호출되는 메서드

        servers가 None이면 빈 리스트로 초기화
        """
        if self.servers is None:
            self.servers = []

@dataclass

class AppConfig:
    """애플리케이션 전체 설정

    모든 외부 시스템 및 서비스의 설정 통합

    Attributes:
        mongo: MongoDB 설정
        chroma: ChromaDB 설정
        llm: LLM 서버 설정
        elastic: Elasticsearch 설정
        velociraptor: Velociraptor 설정
        sleuthkit: SleuthKit 설정
        mcp: MCP 서버 설정
    """
    mongo: MongoConfig
    chroma: ChromaConfig
    llm: LLMConfig
    elastic: ElasticConfig
    velociraptor: VelociraptorConfig
    sleuthkit: SleuthKitConfig
    mcp: MCPConfig

@lru_cache(maxsize=1)

def get_config() -> AppConfig:
    """환경 변수에서 애플리케이션 설정 로드

    싱글톤 패턴 구현으로 첫 호출 이후 캐시된 결과 반환
    환경 변수를 읽어 각 외부 시스템의 설정 객체 생성 및 통합 AppConfig 반환

    로직:
        1. MongoDB 설정 로드 (MONGO_URI, MONGO_DB)
        2. ChromaDB 설정 로드 (CHROMA_DIR)
        3. LLM 설정 로드 (프로필에 따라 local/gpu 분기)
        4. Elasticsearch 설정 로드 (ELASTIC_*)
        5. Velociraptor 설정 로드 (VELO_*)
        6. SleuthKit 설정 로드 (TSK_BIN_DIR)
        7. MCP 서버 설정 로드 (JSON 파일에서)
        8. 모든 설정을 통합하여 AppConfig 생성

    Returns:
        AppConfig: 애플리케이션 전체 설정 객체

    Note:
        @lru_cache 데코레이터로 인해 첫 호출 이후 캐시된 객체 반환
        환경 변수 변경 시 프로세스 재시작 전까지 반영되지 않음
    """
    mongo = MongoConfig(
        uri=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        db=os.getenv("MONGO_DB", "bgent"),
    )
    chroma = ChromaConfig(
        dir=os.getenv("CHROMA_DIR", "./data/chroma")
    )
    profile = os.getenv("LLM_PROFILE", "local").lower()

    if profile == "gpu":
        llm_base = os.getenv("LLM_GPU_BASE_URL", "http://localhost:8000")
        llm_model = os.getenv("LLM_GPU_MODEL", "llama-3.1-8b-instruct")

    else:
        llm_base = os.getenv("LLM_LOCAL_BASE_URL", "http://localhost:8000")
        llm_model = os.getenv("LLM_LOCAL_MODEL", "llama-3.1-8b-instruct")
    llm = LLMConfig(
        base_url=llm_base.rstrip("/"),
        model=llm_model,
        api_key=os.getenv("LLM_API_KEY"),
        api_kind=os.getenv("LLM_API_KIND", "openai"),
        verify_ssl=os.getenv("LLM_VERIFY_SSL", "true").lower() == "true",
        context_size=int(os.getenv("LLM_CONTEXT_SIZE", "4096")),
    )
    elastic = ElasticConfig(
        base_url=os.getenv("ELASTIC_BASE_URL", "http://localhost:9200").rstrip("/"),
        user=os.getenv("ELASTIC_USER", "elastic"),
        password=os.getenv("ELASTIC_PASS", ""),
        default_indices=[s.strip() for s in os.getenv("ELASTIC_DEFAULT_INDICES", "logs-*").split(",") if s.strip()],
        time_field=os.getenv("ELASTIC_TIME_FIELD", "@timestamp"),
        verify_ssl=os.getenv("ELASTIC_VERIFY_SSL", "true").lower() == "true",
    )
    velo = VelociraptorConfig(
        base_url=os.getenv("VELO_BASE_URL", "http://localhost:8889").rstrip("/"),
        api_token=os.getenv("VELO_API_TOKEN", ""),
        verify_ssl=os.getenv("VELO_VERIFY_SSL", "true").lower() == "true",
    )
    tsk = SleuthKitConfig(
        bin_dir=os.getenv("TSK_BIN_DIR", "/usr/bin")
    )
    mcp_enabled = os.getenv("MCP_ENABLED", "false").lower() == "true"
    mcp_servers = []

    if mcp_enabled:
        mcp_config_file = os.getenv("MCP_CONFIG_FILE", "./mcp_servers.json")

        if os.path.exists(mcp_config_file):

            try:
                import json

                with open(mcp_config_file, "r") as f:
                    servers_data = json.load(f)

                    for srv in servers_data.get("servers", []):
                        command = srv.get("command")

                        if command and command.startswith("~/"):
                            command = os.path.expanduser(command)
                        mcp_servers.append(MCPServerConfigItem(
                            name=srv["name"],
                            url=srv.get("url"),
                            command=command,
                            args=srv.get("args"),
                            env=srv.get("env"),
                            headers=srv.get("headers"),
                            enabled=srv.get("enabled", True)
                        ))

            except Exception as e:
                print(f"⚠️  MCP 설정 파일 로드 실패: {e}")
    mcp = MCPConfig(enabled=mcp_enabled, servers=mcp_servers)

    return AppConfig(
        mongo=mongo, chroma=chroma, llm=llm, elastic=elastic,
        velociraptor=velo, sleuthkit=tsk, mcp=mcp
    )

