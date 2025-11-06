import asyncio
import sys
import os
import io
import threading
from typing import List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))


async def send_log(trigger_id: str, message: str):
    from .router import send_log_to_client
    try:
        await send_log_to_client(trigger_id, message)
    except Exception as e:
        print(f"Failed to send log via WebSocket: {e}")


class LogCapture(io.StringIO):
    def __init__(self, trigger_id: str, original_stdout):
        super().__init__()
        self.trigger_id = trigger_id
        self.original_stdout = original_stdout
        self.buffer = ""

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


def execute_agent_sync(conversation_id: str, stage_id: int, trigger_id: str,
                        prompt: str, file_paths: List[str]):
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    try:
        from agent.core.router import run_job

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(send_log(trigger_id, f"[INFO] Agent execution started for conversation: {conversation_id}"))

        data_dir = os.path.join(os.path.dirname(__file__), '../../../../data')
        absolute_file_paths = []

        for filename in file_paths:
            if os.path.isabs(filename):
                absolute_file_paths.append(filename)
            else:
                absolute_path = os.path.join(data_dir, filename)
                if os.path.exists(absolute_path):
                    absolute_file_paths.append(absolute_path)
                    loop.run_until_complete(send_log(trigger_id, f"[INFO] File loaded: {filename}"))
                else:
                    warning_msg = f"[WARNING] File not found: {absolute_path}"
                    print(warning_msg)
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
                stage_id=stage_id
            )
            loop.run_until_complete(send_log(trigger_id, f"[DEBUG] run_job returned: {type(result)}"))
        except Exception as run_job_error:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            error_detail = f"[ERROR] run_job failed: {str(run_job_error)}"
            print(error_detail)
            import traceback
            tb = traceback.format_exc()
            print(tb)
            loop.run_until_complete(send_log(trigger_id, error_detail))
            loop.run_until_complete(send_log(trigger_id, f"[TRACEBACK] {tb}"))
            raise
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

        loop.run_until_complete(send_log(trigger_id, f"[INFO] Agent execution completed"))

    except Exception as e:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        error_msg = f"[ERROR] Agent Execution Error: {str(e)}"
        print(error_msg)
        import traceback
        tb = traceback.format_exc()
        print(tb)

        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(send_log(trigger_id, error_msg))
            loop.run_until_complete(send_log(trigger_id, f"[TRACEBACK] {tb}"))
        except:
            pass


async def execute_agent_async(prompt: str, stage_id: int, file_paths: List[str]):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, execute_agent_sync, prompt, stage_id, file_paths)
