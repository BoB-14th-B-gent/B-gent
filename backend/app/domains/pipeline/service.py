from typing import Any, Dict, List, Optional
import os
import time
import asyncio
import httpx
from fastapi import HTTPException

BACKEND_INTERNAL_URL = os.getenv("BACKEND_INTERNAL_URL")
if not BACKEND_INTERNAL_URL:
    raise RuntimeError("BACKEND_INTERNAL_URL is not set")

AGENT_SERVER_URL = os.getenv("AGENT_SERVER_URL")
if not AGENT_SERVER_URL:
    raise RuntimeError("AGENT_SERVER_URL is not set")

TIMEOUT = httpx.Timeout(connect=10.0, read=1800.0, write=30.0, pool=10.0)

async def _http_json(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> Dict[str, Any]:
    r = await client.request(method, path, **kwargs)
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise HTTPException(
            status_code=502,
            detail={"error_at": path, "status": r.status_code, "detail": detail},
        )
    if "application/json" in (r.headers.get("content-type") or ""):
        return r.json()
    return {}

async def _http_json_agent(method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
    async with httpx.AsyncClient(base_url=AGENT_SERVER_URL, timeout=TIMEOUT) as client:
        r = await client.request(method, path, **kwargs)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise HTTPException(
                status_code=502,
                detail={"error_at": f"AGENT:{path}", "status": r.status_code, "detail": detail},
            )
        if "application/json" in (r.headers.get("content-type") or ""):
            return r.json()
        return {}

def _build_bgent_message_from_structured(structured: Dict[str, Any]) -> str:
    sections = (structured or {}).get("sections") or {}
    exec_list = sections.get("executive summary") or []
    addl_list = sections.get("additional evidence required") or []

    lines: List[str] = []
    lines.append("## 1. Executive Summary")
    if exec_list:
        for s in exec_list:
            lines.append(f"- {s}")
    else:
        lines.append("_No executive summary._")

    lines.append("")
    lines.append("## 6. Additional Evidence Required")
    if addl_list:
        for s in addl_list:
            lines.append(f"- {s}")
    else:
        lines.append("_No additional evidence requested._")

    return "\n".join(lines).strip()

async def _wait_agent_done(
    trigger_id: str,
    poll_interval: float = 2.0,
    timeout: int = 900,
) -> Dict[str, Any]:
    start = time.monotonic()
    last_state: Dict[str, Any] = {}

    while True:
        try:
            state = await _http_json_agent("GET", f"/agent/state/{trigger_id}")
            last_state = state or {}
            status = (state or {}).get("status")
        except HTTPException as e:
            detail = e.detail or {}
            if detail.get("status") == 404:
                status = None
            else:
                raise

        if status in ("done", "error"):
            return last_state

        if time.monotonic() - start > timeout:
            raise HTTPException(
                status_code=504,
                detail={
                    "error": "agent_timeout",
                    "trigger_id": trigger_id,
                    "last_state": last_state,
                },
            )

        await asyncio.sleep(poll_interval)

async def run_pipeline_prepare_service(
    *,
    input_text: str,
    stage_id: int = 0,
    inline_threshold: int = 10 * 1024 * 1024,
    mode: str = "auto",
    conversation_id: Optional[str] = None,
    case_id: Optional[str] = None,
) -> Dict[str, Any]:
    async with httpx.AsyncClient(base_url=BACKEND_INTERNAL_URL, timeout=TIMEOUT) as client:
        existing_conv = conversation_id is not None

        if not existing_conv:
            if not case_id:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "case_id is required when conversation_id is not provided"},
                )

            conv_res = await _http_json(
                client,
                "POST",
                f"/cases/{case_id}/conversations",
                json={"input": input_text},
            )
            conversation_id = (
                conv_res.get("_id")
                or conv_res.get("id")
                or conv_res.get("conversation_id")
            )
            if not conversation_id:
                raise HTTPException(
                    500,
                    detail={"error": "conversation_id missing", "response": conv_res},
                )
        else:
            await _http_json(
                client,
                "PATCH",
                f"/conversations/{conversation_id}/stage",
                params={"stage_id": stage_id},
            )
            await _http_json(
                client,
                "POST",
                f"/conversations/{conversation_id}/messages",
                json={
                    "role": "USER",
                    "stage_id": stage_id,
                    "content": input_text,
                },
            )

        trg_res = await _http_json(
            client,
            "POST",
            "/triggers",
            json={"conversation_id": conversation_id, "stage_id": stage_id},
        )
        trigger_id = trg_res.get("trigger_id")
        if not trigger_id:
            raise HTTPException(
                500,
                detail={"error": "trigger_id missing", "response": trg_res},
            )

        ev_res = await _http_json(
            client,
            "POST",
            "/evidences/input",
            json={
                "conversation_id": conversation_id,
                "stage_id": stage_id,
                "mode": mode,
                "inline_threshold": inline_threshold,
            },
        )
        prompt_id: Optional[str] = ev_res.get("prompt_id")
        items: List[Dict[str, Any]] = ev_res.get("items") or []

        if prompt_id:
            await _http_json(
                client,
                "PATCH",
                f"/triggers/{trigger_id}/prompt",
                json={"prompt_id": prompt_id},
            )

        evidence_refs = [
            {"collection": "INPUT_EVIDENCES", "id": it["evidence_id"]}
            for it in items
            if it.get("evidence_id")
        ]
        if evidence_refs:
            await _http_json(
                client,
                "PATCH",
                f"/triggers/{trigger_id}/evidences",
                json={"evidences": evidence_refs},
            )

    agent_call_res = await _http_json_agent(
        "POST",
        "/agent",
        json={"trigger_id": trigger_id},
    )
    if not agent_call_res.get("ok", False):
        print(f"[pipeline] AGENT /agent returned non-ok for trigger {trigger_id}: {agent_call_res}")

    return {
        "conversation_id": conversation_id,
        "trigger_id": trigger_id,
        "prompt_id": prompt_id,
    }

async def run_after_agent_and_create_report(
    trigger_id: str,
) -> Dict[str, Any]:
    async with httpx.AsyncClient(base_url=BACKEND_INTERNAL_URL, timeout=TIMEOUT) as client:
        trg = await _http_json(client, "GET", f"/triggers/{trigger_id}")
        conversation_id = trg.get("conversation_id")
        if isinstance(conversation_id, dict) and "$oid" in conversation_id:
            conversation_id = conversation_id["$oid"]
        
        prompt_id = trg.get("prompt_id")
        if isinstance(prompt_id, dict) and "$oid" in prompt_id:
            prompt_id = prompt_id["$oid"]
        
        stage_id = trg.get("stage_id", 0)

        mcp_list = await _http_json(
            client,
            "GET",
            "/evidences/mcp",
            params={"conversation_id": conversation_id, "stage_id": stage_id},
        )
        mcp_items: List[Dict[str, Any]] = mcp_list.get("items") or []

        mcp_refs = [
            {"collection": "MCP_EVIDENCES", "id": it["_id"]}
            for it in mcp_items
            if it.get("_id")
        ]
        if mcp_refs:
            await _http_json(
                client,
                "PATCH",
                f"/triggers/{trigger_id}/evidences",
                json={"evidences": mcp_refs},
            )

        sllm = await _http_json(
            client,
            "POST",
            "/sllm/reports",
            json={"trigger_id": trigger_id},
        )
        report_id = sllm.get("report_id")
        if not report_id:
            raise HTTPException(
                500,
                detail={"error": "report_id missing from sLLM", "response": sllm},
            )

        rep_doc = await _http_json(client, "GET", f"/reports/{report_id}")
        report_text: str = rep_doc.get("report") or ""

        patched = await _http_json(
            client,
            "PATCH",
            f"/reports/{report_id}/structured",
            json={},
        )
        structured: Dict[str, Any] = patched.get("structured") or {}

        await _http_json(
            client,
            "PATCH",
            f"/triggers/{trigger_id}/report",
            json={"report_id": report_id},
        )

        bgent_msg = _build_bgent_message_from_structured(structured)
        if bgent_msg:
            await _http_json(
                client,
                "POST",
                f"/conversations/{conversation_id}/messages",
                json={
                    "role": "B-GENT",
                    "stage_id": stage_id,
                    "content": bgent_msg,
                },
            )

    return {
        "conversation_id": conversation_id,
        "trigger_id": trigger_id,
        "prompt_id": prompt_id,
        "report_id": report_id,
        "report": report_text,
    }

async def run_pipeline_full_service(
    *,
    input_text: str,
    stage_id: int = 0,
    inline_threshold: int = 10 * 1024 * 1024,
    mode: str = "auto",
    conversation_id: Optional[str] = None,
    case_id: Optional[str] = None,
) -> Dict[str, Any]:
    base = await run_pipeline_prepare_service(
        input_text=input_text,
        stage_id=stage_id,
        inline_threshold=inline_threshold,
        mode=mode,
        conversation_id=conversation_id,
        case_id=case_id,
    )
    conversation_id = base["conversation_id"]
    trigger_id = base["trigger_id"]
    prompt_id = base.get("prompt_id")

    try:
        agent_state = await _wait_agent_done(
            trigger_id=trigger_id,
            poll_interval=2.0,
            timeout=900,
        )
    except HTTPException as exc:
        print(f"[pipeline] Agent wait failed for trigger {trigger_id}: {exc.detail}")

    async with httpx.AsyncClient(base_url=BACKEND_INTERNAL_URL, timeout=TIMEOUT) as client:
        mcp_list = await _http_json(
            client,
            "GET",
            f"/evidences/mcp",
            params={"conversation_id": conversation_id, "stage_id": stage_id},
        )

        mcp_items: List[Dict[str, Any]] = mcp_list.get("items") or []

        mcp_refs = [
            {"collection": "MCP_EVIDENCES", "id": it["_id"]}
            for it in mcp_items
            if it.get("_id")
        ]
        if mcp_refs:
            await _http_json(
                client,
                "PATCH",
                f"/triggers/{trigger_id}/evidences",
                json={"evidences": mcp_refs}
            )

    async with httpx.AsyncClient(base_url=BACKEND_INTERNAL_URL, timeout=TIMEOUT) as client:
        sllm = await _http_json(
            client,
            "POST",
            "/sllm/reports",
            json={"trigger_id": trigger_id},
        )
        report_id = sllm.get("report_id")
        if not report_id:
            raise HTTPException(
                500,
                detail={"error": "report_id missing from sLLM", "response": sllm},
            )

        rep_doc = await _http_json(client, "GET", f"/reports/{report_id}")
        report_text: str = rep_doc.get("report") or ""

        patched = await _http_json(
            client,
            "PATCH",
            f"/reports/{report_id}/structured",
            json={},
        )
        structured: Dict[str, Any] = patched.get("structured") or {}

        await _http_json(
            client,
            "PATCH",
            f"/triggers/{trigger_id}/report",
            json={"report_id": report_id},
        )

        bgent_msg = _build_bgent_message_from_structured(structured)
        if bgent_msg:
            await _http_json(
                client,
                "POST",
                f"/conversations/{conversation_id}/messages",
                json={
                    "role": "B-GENT",
                    "stage_id": stage_id,
                    "content": bgent_msg,
                },
            )

    return {
        "conversation_id": conversation_id,
        "trigger_id": trigger_id,
        "prompt_id": prompt_id,
        "report_id": report_id,
        "report": report_text,
    }

async def run_pipeline_service(
    *,
    input_text: str,
    stage_id: int = 0,
    inline_threshold: int = 10 * 1024 * 1024,
    mode: str = "auto",
    conversation_id: Optional[str] = None,
    case_id: Optional[str] = None,
) -> Dict[str, Any]:
    return await run_pipeline_full_service(
        input_text=input_text,
        stage_id=stage_id,
        inline_threshold=inline_threshold,
        mode=mode,
        conversation_id=conversation_id,
        case_id=case_id,
    )