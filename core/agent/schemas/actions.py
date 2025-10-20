"""액션 관련 스키마 모듈

액션(Action)과 실행 결과(ActionResult) 데이터 구조 정의
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

@dataclass

class Action:
    """실행할 액션"""
    tool: str
    operation: str
    params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    retry_count: int = 0
    timeout_seconds: int = 60

    def to_dict(self) -> Dict[str, Any]:

        return {
            "tool": self.tool,
            "operation": self.operation,
            "params": self.params,
            "reason": self.reason,
            "retry_count": self.retry_count,
            "timeout_seconds": self.timeout_seconds
        }

@dataclass

class ActionResult:
    """액션 실행 결과"""
    action: Action
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:

        return {
            "action": self.action.to_dict(),
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "execution_time_seconds": self.execution_time_seconds,
            "timestamp": self.timestamp
        }

