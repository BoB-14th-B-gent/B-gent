import os, httpx

SLLM_BASE_URL     = os.getenv("SLLM_BASE_URL")
SLLM_API_KEY      = os.getenv("SLLM_API_KEY")
SLLM_PATH_ANALYZE = os.getenv("SLLM_PATH_ANALYZE")

async def request_report_creation(trigger_id: str) -> str:
    if not trigger_id:
        raise ValueError("trigger_id is required")

    url = f"{SLLM_BASE_URL.rstrip('/')}{SLLM_PATH_ANALYZE}"
    headers = {"x-api-key": SLLM_API_KEY, "Content-Type": "application/json"}
    timeout = httpx.Timeout(connect=5.0, read=1800.0, write=60.0, pool=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json={"trigger_id": trigger_id}, headers=headers)
        r.raise_for_status()
        data = r.json()

    rid = data.get("report_id") or data.get("_id") or data.get("id")
    if not rid:
        raise RuntimeError(f"sLLM returned no report_id: {data}")
    return rid