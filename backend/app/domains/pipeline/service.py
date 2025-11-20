from typing import Any, Dict, List, Optional
import os
import httpx
from fastapi import HTTPException

BACKEND_INTERNAL_URL = os.getenv("BACKEND_INTERNAL_URL")
if not BACKEND_INTERNAL_URL:
    raise RuntimeError("BACKEND_INTERNAL_URL is not set")

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

async def run_pipeline_service(*, input_text: str, stage_id: int = 0, inline_threshold: int = 10 * 1024 * 1024, mode: str = "auto", conversation_id: Optional[str] = None) -> Dict[str, Any]:
    async with httpx.AsyncClient(base_url=BACKEND_INTERNAL_URL, timeout=TIMEOUT) as client:
        existing_conv = conversation_id is not None

        if not conversation_id:
            conv_res = await _http_json(
                client, "POST", "/conversations", json={"input": input_text}
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

        if existing_conv:
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
                500, detail={"error": "trigger_id missing", "response": trg_res}
            )

        ev_res = await _http_json(
            client,
            "POST",
            "/evidences/input",
            json={
                "conversation_id": conversation_id,
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

        sllm = await _http_json(
            client, "POST", "/sllm/reports", json={"trigger_id": trigger_id}
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
            client, "PATCH", f"/reports/{report_id}/structured", json={}
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