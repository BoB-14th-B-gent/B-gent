import asyncio
import sys
import os
import io
from typing import List, Tuple, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from ..utils.debug import debug_print

try:
    BASE_DIR = Path(__file__).resolve().parents[2]
    ENV_PATH = BASE_DIR / ".env"

    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)
        debug_print(f"[agent.service] .env loaded: {ENV_PATH}")
    else:
        debug_print(f"[agent.service] .env NOT FOUND at: {ENV_PATH}")
except Exception as e:
    debug_print(f"[agent.service] dotenv load skipped: {e}")

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")

_mongo_client: MongoClient | None = None

def get_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI)
        debug_print(f"[agent.service] connected → {MONGO_URI} / db={MONGO_DB}")
    return _mongo_client[MONGO_DB]

def get_agent_state_from_db(trigger_id: str) -> Dict[str, Any]:
    db = get_db()
    col = db["AGENT_STATES"]

    doc = col.find_one({"trigger_id": ObjectId(trigger_id)}, sort=[("updated_at", -1)])
    if not doc:
        return {}

    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("trigger_id"), ObjectId):
        doc["trigger_id"] = str(doc["trigger_id"])
    if isinstance(doc.get("conversation_id"), ObjectId):
        doc["conversation_id"] = str(doc["conversation_id"])

    return doc

async def send_log(trigger_id: str, message: str):
    from .router import send_log_to_client
    try:
        await send_log_to_client(trigger_id, message)
    except Exception as e:
        debug_print(f"Failed to send log via WebSocket: {e}")

class LogCapture(io.StringIO):
    def __init__(self, trigger_id: str, original_stdout):
        super().__init__()
        self.trigger_id = trigger_id
        self.original_stdout = original_stdout

    def write(self, text):
        self.original_stdout.write(text)
        self.original_stdout.flush()

        if text and text.strip():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(send_log(self.trigger_id, text.rstrip()))
                loop.close()
            except Exception as e:
                self.original_stdout.write(f"[LogCapture Error] {e}\n")

        return len(text)

    def flush(self):
        self.original_stdout.flush()

def _load_trigger_and_prompt(trigger_id: str) -> Tuple[str, int, str, List[str]]:
    db = get_db()
    triggers_col = db["TRIGGERS"]
    prompts_col = db["PROMPTS"]

    try:
        trigger_obj_id = ObjectId(trigger_id)
    except Exception:
        trigger = triggers_col.find_one({"_id": trigger_id})
    else:
        trigger = triggers_col.find_one({"_id": trigger_obj_id})

    if not trigger:
        raise RuntimeError(f"Trigger not found for id={trigger_id}")

    conv_raw = trigger.get("conversation_id")
    if isinstance(conv_raw, ObjectId):
        conversation_id = str(conv_raw)
    else:
        conversation_id = str(conv_raw)

    stage_id = int(trigger.get("stage_id", 0))

    prompt_raw = trigger.get("prompt_id")
    if isinstance(prompt_raw, ObjectId):
        prompt_obj_id = prompt_raw
    else:
        try:
            prompt_obj_id = ObjectId(prompt_raw)
        except Exception:
            prompt_obj_id = prompt_raw

    if isinstance(prompt_obj_id, ObjectId):
        prompt_doc = prompts_col.find_one({"_id": prompt_obj_id})
    else:
        prompt_doc = prompts_col.find_one({"_id": prompt_obj_id})

    if not prompt_doc:
        raise RuntimeError(f"Prompt not found for trigger={trigger_id}")

    user_prompt = prompt_doc.get("user_prompt", "")
    unprocessed_filenames = prompt_doc.get("unprocessed_filenames", []) or []

    return conversation_id, stage_id, user_prompt, unprocessed_filenames

def execute_agent_sync(trigger_id: str):
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    try:
        from agent.core.router import run_job

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(send_log(trigger_id, f"[INFO] Agent execution started for trigger: {trigger_id}"))

        try:
            conversation_id, stage_id, prompt, file_paths = _load_trigger_and_prompt(trigger_id)
            loop.run_until_complete(send_log(trigger_id, f"[DEBUG] Loaded from MongoDB → conv={conversation_id}, stage={stage_id}, files={file_paths}"))
        except Exception as db_error:
            err_msg = f"[ERROR] Failed to load trigger/prompt from MongoDB: {db_error}"
            debug_print(err_msg)
            loop.run_until_complete(send_log(trigger_id, err_msg))
            loop.close()
            return

        data_dir = os.path.join(os.path.dirname(__file__), '../../data')
        absolute_file_paths: List[str] = []

        for filename in file_paths:
            if not filename or not filename.strip():
                continue

            if os.path.isabs(filename):
                absolute_file_paths.append(filename)
            else:
                absolute_path = os.path.join(data_dir, filename)
                if os.path.exists(absolute_path):
                    absolute_file_paths.append(absolute_path)
                    loop.run_until_complete(send_log(trigger_id, f"[INFO] File loaded: {filename}"))
                else:
                    warning_msg = f"[WARNING] File not found: {absolute_path}"
                    debug_print(warning_msg)
                    loop.run_until_complete(send_log(trigger_id, warning_msg))

        loop.run_until_complete(send_log(trigger_id, f"[INFO] Running analysis with {len(absolute_file_paths)} files..."))

        log_capture = LogCapture(trigger_id, original_stdout)
        sys.stdout = log_capture
        sys.stderr = log_capture

        try:
            loop.run_until_complete(send_log(trigger_id, f"[DEBUG] Calling run_job..."))
            result = run_job(
                user_prompt=prompt,
                file_paths=absolute_file_paths,
                generate_report_flag=False,
                conversation_id=conversation_id,
                trigger_id=trigger_id,
                stage_id=stage_id,
            )
            loop.run_until_complete(send_log(trigger_id, f"[DEBUG] run_job returned: {type(result)}"))
        except Exception as run_job_error:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            error_detail = f"[ERROR] run_job failed: {str(run_job_error)}"
            debug_print(error_detail)
            import traceback
            tb = traceback.format_exc()
            debug_print(tb)
            loop.run_until_complete(send_log(trigger_id, error_detail))
            loop.run_until_complete(send_log(trigger_id, f"[TRACEBACK] {tb}"))
            raise
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

        loop.run_until_complete(send_log(trigger_id, f"[INFO] Agent execution completed"))
        loop.close()

    except Exception as e:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        error_msg = f"[ERROR] Agent Execution Error: {str(e)}"
        debug_print(error_msg)
        import traceback
        tb = traceback.format_exc()
        debug_print(tb)

        try:
            error_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(error_loop)
            error_loop.run_until_complete(send_log(trigger_id, error_msg))
            error_loop.run_until_complete(send_log(trigger_id, f"[TRACEBACK] {tb}"))
            error_loop.close()
        except:
            pass

async def execute_agent_async(trigger_id: str):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, execute_agent_sync, trigger_id)