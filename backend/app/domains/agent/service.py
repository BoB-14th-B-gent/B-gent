import asyncio
import sys
import os
from typing import List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))


def execute_agent_sync(conversation_id: str, stage_id: int, trigger_id: str,
                        prompt: str, file_paths: List[str]):
    try:
        from agent.core.router import run_job

        data_dir = os.path.join(os.path.dirname(__file__), '../../../../data')
        absolute_file_paths = []

        for filename in file_paths:
            if os.path.isabs(filename):
                absolute_file_paths.append(filename)
            else:
                absolute_path = os.path.join(data_dir, filename)
                if os.path.exists(absolute_path):
                    absolute_file_paths.append(absolute_path)
                else:
                    print(f"Warning: File not found: {absolute_path}")

        result = run_job(
            user_prompt=prompt,
            file_paths=absolute_file_paths,
            generate_report_flag=False,
            conversation_id=conversation_id,
            trigger_id=trigger_id,
            stage_id=stage_id
        )

    except Exception as e:
        print(f"[Agent Execution Error] {str(e)}")
        import traceback
        traceback.print_exc()


async def execute_agent_async(prompt: str, stage_id: int, file_paths: List[str]):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, execute_agent_sync, prompt, stage_id, file_paths)
