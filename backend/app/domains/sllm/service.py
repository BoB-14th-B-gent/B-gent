import os
from typing import Dict, Any
import httpx

API_KEY = os.getenv("API_KEY")
SLLM_URL = os.getenv("SLLM_URL")

def _normalized_endpoint() -> str:
    if not SLLM_URL:
        raise RuntimeError("SLLM_URL is not set")
    url = SLLM_URL.strip()
    if url.endswith("/analyze_trigger"):
        return url

    if url.endswith("/"):
        return url + "analyze_trigger"
    return url + "/analyze_trigger"

async def request_report_creation(trigger_id: str) -> str:
    if not trigger_id:
        raise ValueError("trigger_id is required")

    endpoint = _normalized_endpoint()
    headers = {"x-api-key": API_KEY} if API_KEY else {}
    payload: Dict[str, Any] = {"trigger_id": trigger_id}

    timeout = httpx.Timeout(30.0, read=120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(endpoint, json=payload, headers=headers)
        if resp.status_code != 200:
            try:
                detail = resp.json()
            except Exception:
                detail = {"error": resp.text}
            raise ValueError(f"sLLM request failed ({resp.status_code}): {detail}")

        data = resp.json()
        rid = data.get("report_id")
        if not rid:
            raise ValueError(f"invalid sLLM response: {data}")
        return rid