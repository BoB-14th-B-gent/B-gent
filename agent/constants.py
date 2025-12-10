"""
상수 정의 모듈
"""

# 실행 관련 상수
DEFAULT_TIMEOUT = 120  
SHORT_TIMEOUT = 30  
MEDIUM_TIMEOUT = 60  
LONG_TIMEOUT = 180  
VERY_LONG_TIMEOUT = 300  

DEFAULT_RETRY_COUNT = 2  
MAX_RETRY_COUNT = 5  
MIN_BACKOFF_SECONDS = 1  
MAX_BACKOFF_SECONDS = 10  

# ReAct 에이전트 관련 상수
MAX_REACT_ITERATIONS = 30  
MAX_SAME_ACTION_RETRIES = 2  
MAX_SAME_TOOL_CALLS = 5  

# LLM 관련 상수
LLM_TEMPERATURE_DEFAULT = 0.0 
LLM_TEMPERATURE_CREATIVE = 0.7 

LLM_MAX_TOKENS_DEFAULT = 4096
LLM_MAX_TOKENS_LARGE = 8192

# RAG 관련 상수
RAG_TOP_K = 10  
RAG_SIMILARITY_THRESHOLD = 0.5  

# 출력 관련 상수
PREVIEW_MAX_LENGTH = 1000  
PREVIEW_MAX_LINES = 50  

# 에러 패턴
RETRYABLE_ERROR_PATTERNS = [
    "connection",
    "timeout",
    "temporary",
    "unavailable",
    "network",
    "refused",
    "reset",
]

# 작업 타입 관련
DISK_IMAGE_EXTENSIONS = [".dd", ".raw", ".img", ".e01", ".aff"]
PE_FILE_EXTENSIONS = [".exe", ".dll", ".sys"]
LOG_FILE_EXTENSIONS = [".log", ".evtx", ".txt"]
ARCHIVE_EXTENSIONS = [".zip", ".tar", ".gz", ".7z"]

# MongoDB 컬렉션 이름
COLLECTION_AGENT_STATES = "agent_states"
COLLECTION_MCP_EVIDENCES = "mcp_evidences"
COLLECTION_MCP_CAPABILITIES = "mcp_capabilities"

# 기타 상수
SEPARATOR = "-" * 60
DOUBLE_SEPARATOR = "=" * 60