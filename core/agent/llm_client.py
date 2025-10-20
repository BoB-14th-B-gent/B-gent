"""LLM 클라이언트 모듈

OpenAI/Ollama 호환 LLM API 호출 제공
"""
from __future__ import annotations
import requests, json
from typing import List, Dict, Any, Optional
from .config import get_config
_cfg = get_config()

class LLMClient:

    def __init__(self):
        self.base = _cfg.llm.base_url
        self.verify = _cfg.llm.verify_ssl
        self.model = _cfg.llm.model
        self.api_key = _cfg.llm.api_key
        self.kind = (_cfg.llm.api_kind or "openai").lower()
        self._resolved_kind: Optional[str] = None

    def _headers(self):
        h = {"Content-Type": "application/json"}

        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"

        return h

    def _try_openai_chat(self, messages: List[Dict[str, str]], response_format_json: bool, timeout: int) -> Dict[str, Any]:
        url = f"{self.base}/v1/chat/completions"
        payload = {"model": self.model, "messages": messages, "temperature": 0.1}

        if response_format_json:
            payload["response_format"] = {"type": "json_object"}
        r = requests.post(url, json=payload, headers=self._headers(), timeout=timeout, verify=self.verify)

        if r.status_code == 404:
            raise FileNotFoundError("openai_chat_404")
        r.raise_for_status()

        return r.json()

    def _try_openai_completions(self, messages: List[Dict[str, str]], timeout: int) -> Dict[str, Any]:
        url = f"{self.base}/v1/completions"
        prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        payload = {"model": self.model, "prompt": prompt, "temperature": 0.1}
        r = requests.post(url, json=payload, headers=self._headers(), timeout=timeout, verify=self.verify)

        if r.status_code == 404:
            raise FileNotFoundError("openai_completions_404")
        r.raise_for_status()
        text = r.json().get("choices", [{}])[0].get("text", "")

        return {"choices":[{"message":{"content":text}}]}

    def _try_ollama_chat(self, messages: List[Dict[str, str]], response_format_json: bool, timeout: int) -> Dict[str, Any]:
        url = f"{self.base}/api/chat"

        if response_format_json:
            messages = messages.copy()
            if messages:
                last_msg = messages[-1]

                if last_msg.get("role") == "user":
                    messages[-1] = {
                        "role": "user",
                        "content": f"{last_msg['content']}\n\nIMPORTANT: Respond with ONLY valid JSON. No explanations, no markdown code blocks, just raw JSON."
                    }
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json" if response_format_json else None,
            "options": {
                "num_ctx": _cfg.llm.context_size
            }
        }
        r = requests.post(url, json=payload, headers=self._headers(), timeout=timeout, verify=self.verify)

        if r.status_code == 404:
            raise FileNotFoundError("ollama_chat_404")
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "")

        return {"choices":[{"message":{"content":content}}]}

    def chat(self, messages: List[Dict[str, str]], response_format_json: bool = True, timeout: int = 60) -> Dict[str, Any]:
        """LLM API 호출 (자동 폴백 지원)

        Args:
            messages: 메시지 리스트 [{"role": "user", "content": "..."}, ...]
            response_format_json: JSON 응답 형식 요청 여부 (기본값: True)
            timeout: 타임아웃 (초, 기본값: 60)

        Returns:
            Dict[str, Any]: LLM 응답
                {"choices": [{"message": {"content": "..."}}]}

        Raises:
            RuntimeError: 모든 폴백 시도 실패 시
        """
        try_order = []

        if self.kind == "openai":
            try_order = [
                (self._try_openai_chat, True),
                (self._try_openai_completions, False),
                (self._try_ollama_chat, True)
            ]

        elif self.kind == "ollama":
            try_order = [
                (self._try_ollama_chat, True),
                (self._try_openai_chat, True),
                (self._try_openai_completions, False)
            ]

        else:
            try_order = [
                (self._try_openai_chat, True),
                (self._try_ollama_chat, True),
                (self._try_openai_completions, False)
            ]
        last_err = None

        for fn, supports_json in try_order:

            try:

                if supports_json:

                    return fn(messages, response_format_json, timeout)

                else:

                    return fn(messages, timeout)

            except FileNotFoundError:
                last_err = "404"
                continue

            except Exception as e:
                last_err = str(e)
                continue
        raise RuntimeError(f"LLM chat failed across attempts: {last_err}")

