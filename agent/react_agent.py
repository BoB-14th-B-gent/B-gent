"""ReAct Pattern Agent

Claude와 유사하게 Think → Act → Observe 루프로 동작하는 에이전트
"""
from __future__ import annotations
import json
import time
from typing import Dict, Any, List, Optional
from .llm_client import LLMClient
from .mcp_singleton import get_mcp_client
from .rag import query_mcp_candidates


class ReActAgent:
    """추론 기반 에이전트 (Think → Act → Observe 반복)"""

    def __init__(self):
        self.llm = LLMClient()
        self.max_iterations = 20
        self.context = {
            "prompt": "",
            "observations": [],
            "finished": False,
            "answer": None,
            "termination_reason": None  # "max_iterations", "duplicate_actions", "natural", "no_action"
        }
        self.available_tools = []  # RAG 검색 결과 캐싱

    def run(self, user_prompt: str, file_paths: List[str] = None, job_id: str = None) -> Dict[str, Any]:
        """ReAct 루프 실행

        Args:
            user_prompt: 사용자 요청
            file_paths: 파일 경로 리스트 (선택)
            job_id: 작업 ID (MongoDB 로깅용, 선택)

        Returns:
            Dict: 실행 결과
                - answer: 최종 답변
                - observations: 관찰 기록
                - iterations: 반복 횟수
        """
        self.context = {
            "prompt": user_prompt,
            "file_paths": file_paths or [],
            "job_id": job_id,
            "observations": [],
            "finished": False,
            "answer": None,
            "termination_reason": None
        }

        print("\n" + "=" * 80)
        print("[ReAct Agent] Starting iterative reasoning...")
        print("=" * 80)

        # RAG 검색은 처음 한 번만 실행 (매번 실행하면 너무 느림)
        print("\n[RAG] Searching relevant tools from knowledge base...")
        start_rag = time.time()
        self.available_tools = self._get_available_tools()
        print(f"[RAG] Found {len(self.available_tools)} tools in {time.time() - start_rag:.2f}s")

        iteration = 0
        start_time = time.time()
        while not self.context["finished"] and iteration < self.max_iterations:
            iteration += 1
            elapsed = time.time() - start_time
            print(f"\n{'='*80}")
            print(f"[Iteration {iteration}/{self.max_iterations}] (Elapsed: {elapsed:.1f}s)")
            print(f"{'='*80}")

            try:
                # 1. Think: 다음 행동 결정
                thought_result = self._think()

                if thought_result.get("finished"):
                    self.context["finished"] = True
                    self.context["answer"] = thought_result.get("answer", "")
                    self.context["termination_reason"] = "natural"
                    print(f"\n[Finished] {thought_result.get('thought', '')}")
                    break

                # 2. Act: 도구 실행
                action = thought_result.get("action")
                if not action:
                    print("[Warning] No action generated, finishing...")
                    self.context["finished"] = True
                    self.context["termination_reason"] = "no_action"
                    break

                # [REMOVED] 카테고리 차단 로직 제거
                # 이유: 잘못된 첫 선택 시 복구 불가능하게 만듦
                # 대신 프롬프트로 유도하는 것이 더 효과적

                # 성공한 액션 반복 감지 및 차단 (같은 파라미터로 반복 시에만)
                action_name = f"{action['tool']}.{action['operation']}"
                current_params = str(action.get('params', {}))  # 파라미터 문자열화

                # 이미 성공한 적 있는지 확인 (현재 시도는 제외)
                if self.context["observations"]:  # observations가 있을 때만
                    identical_success_count = 0
                    for obs in self.context["observations"][-5:]:  # 최근 5개 확인
                        prev_action_name = f"{obs['action']['tool']}.{obs['action']['operation']}"
                        prev_params = str(obs['action'].get('params', {}))

                        # 액션 이름 AND 파라미터가 동일하고 성공했을 때만 카운트
                        if (action_name == prev_action_name and
                            current_params == prev_params and
                            ("'success': True" in obs['observation'] or '"success": true' in obs['observation'].lower())):
                            identical_success_count += 1

                    # 완전히 동일한 액션(파라미터 포함)이 이미 2번 성공했으면 차단
                    if identical_success_count >= 2:
                        print(f"\n⚠️ [CRITICAL] Identical action {action_name} with same params already succeeded {identical_success_count} times!")
                        print(f"⚠️ Params: {current_params[:100]}...")
                        print(f"⚠️ This is wasting iterations. Forcing completion...")

                        # 강제로 분석 완료 처리 - LLM에게 분석 요청
                        self.context["finished"] = True
                        self.context["termination_reason"] = "duplicate_actions"
                        self.context["answer"] = self._force_analysis_from_observations()
                        break

                observation = self._act(action)

                # 3. Record observation
                self.context["observations"].append({
                    "iteration": iteration,
                    "thought": thought_result.get("thought", ""),
                    "action": action,
                    "observation": observation
                })

            except Exception as e:
                print(f"\n[Error] {str(e)}")
                import traceback
                traceback.print_exc()
                break

        # 최대 반복 횟수 도달 체크
        if iteration >= self.max_iterations and not self.context["finished"]:
            self.context["termination_reason"] = "max_iterations"

        print("\n" + "=" * 80)
        print(f"[ReAct Agent] Completed in {iteration} iterations")
        print("=" * 80)

        # If we didn't finish naturally, generate a summary from observations
        final_answer = self.context.get("answer")
        if not final_answer and self.context["observations"]:
            final_answer = self._generate_summary_from_observations()
        elif not final_answer:
            final_answer = "No analysis performed - no tools were executed."

        return {
            "answer": final_answer,
            "observations": self.context["observations"],
            "iterations": iteration,
            "success": self.context["finished"]
        }

    def _think(self) -> Dict[str, Any]:
        """사고 단계: LLM이 다음 행동 결정

        Returns:
            Dict:
                - thought: 사고 내용
                - action: 다음 행동 (tool, operation, params)
                - finished: 완료 여부
                - answer: 최종 답변 (finished=True인 경우)
        """
        # 캐시된 도구 리스트 사용 (RAG는 run()에서 한 번만 실행)
        prompt = self._build_thinking_prompt(self.available_tools)

        print("\n[Thinking] Analyzing current situation and deciding next step...")
        think_start = time.time()

        try:
            response = self.llm.chat(
                [{"role": "user", "content": prompt}],
                response_format_json=True,
                timeout=120
            )

            think_elapsed = time.time() - think_start
            print(f"[Thinking] Completed in {think_elapsed:.2f}s")

            content = response["choices"][0]["message"]["content"]
            result = json.loads(content)

            # LLM 응답 검증 및 수정
            if not result.get("finished") and "action" in result:
                action = result["action"]
                tool = action.get("tool", "")
                operation = action.get("operation", "")

                # 1. 앞에 붙은 '.' 제거
                if tool.startswith("."):
                    print(f"[Validation] Fixing invalid tool name: '{tool}' → '{tool[1:]}'")
                    action["tool"] = tool[1:]
                    tool = action["tool"]

                # 2. 도구명에 operation이 중복 포함된 경우 수정
                if "." in operation:
                    parts = operation.split(".")
                    print(f"[Validation] Fixing invalid operation: '{operation}' → '{parts[-1]}'")
                    action["operation"] = parts[-1]

                # 3. 사용 가능한 도구 리스트에서 검증
                valid_tools = {f"{t['server']}.{t['tool_name']}" for t in self.available_tools}
                current_tool = f"{action['tool']}.{action['operation']}"
                if current_tool not in valid_tools and valid_tools:
                    print(f"[Warning] Tool '{current_tool}' not in available tools list")
                    print(f"[Warning] Available tools: {list(valid_tools)[:5]}...")

            thought = result.get("thought", "")
            print(f"\n[Thought] {thought}")

            return result

        except Exception as e:
            print(f"\n[Error in thinking] {str(e)}")
            return {"finished": True, "thought": "Error occurred", "answer": f"Error: {str(e)}"}

    def _act(self, action: Dict[str, Any]) -> str:
        """행동 단계: 도구 실행

        Args:
            action: 실행할 행동
                - tool: 서버 이름 (elastic, sleuthkit, etc.)
                - operation: 도구 이름
                - params: 파라미터

        Returns:
            str: 관찰 결과
        """
        tool = action.get("tool")
        operation = action.get("operation")
        params = action.get("params", {})

        print(f"\n[Action] Calling {tool}.{operation}")
        print(f"[Params] {json.dumps(params, indent=2, ensure_ascii=False)}")

        try:
            start_time = time.time()

            # MCP 도구 실행
            mcp_client = get_mcp_client()
            result = mcp_client.call_tool(tool, operation, params, timeout=120)

            elapsed = time.time() - start_time

            # MongoDB에 로깅
            from .storage.evidence_logger import log_mcp_execution
            success = result.get("success", False) if isinstance(result, dict) else True
            result_data = result.get("result") if isinstance(result, dict) else result

            log_mcp_execution(
                mcp_name=tool,
                tool_name=operation,
                request=params,
                response=result_data,
                success=success,
                job_id=self.context.get("job_id")
            )

            # 결과를 문자열로 변환 (너무 길면 잘라냄)
            result_str = str(result)
            if len(result_str) > 5000:
                result_str = result_str[:5000] + "\n\n...(truncated)"

            print(f"\n[Observation] Completed in {elapsed:.2f}s")
            print(f"[Result Preview] {result_str[:500]}...")

            return result_str

        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            print(f"\n[Error] {error_msg}")

            # 실패도 MongoDB에 로깅
            from .storage.evidence_logger import log_mcp_execution
            log_mcp_execution(
                mcp_name=tool,
                tool_name=operation,
                request=params,
                response=str(e),
                success=False,
                job_id=self.context.get("job_id")
            )

            return error_msg

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """RAG에서 사용 가능한 도구 검색"""
        # 사용자 프롬프트에서 키워드 추출 및 강화
        prompt = self.context["prompt"].lower()

        # SIEM/로그 관련 키워드 강화
        if any(kw in prompt for kw in ["siem", "log", "malicious", "악성", "event", "elasticsearch"]):
            search_text = f"elasticsearch SIEM log search query index {self.context['prompt']}"
        else:
            search_text = self.context["prompt"]

        # 사용자 프롬프트 기반으로 관련 도구 검색
        candidates = query_mcp_candidates(
            text=search_text,
            top_k=15  # 30에서 15로 줄임 - 프롬프트 크기 감소
        )

        tools = []
        for cand in candidates:
            meta = cand.get("meta", {})
            if meta.get("is_mcp"):
                try:
                    schema_str = meta.get("input_schema", "{}")
                    schema = json.loads(schema_str) if isinstance(schema_str, str) else schema_str
                except:
                    schema = {}

                tools.append({
                    "server": meta.get("server", "unknown"),
                    "tool_name": meta.get("tool_name", "unknown"),
                    "description": meta.get("description", ""),
                    "input_schema": schema
                })

        return tools

    def _build_thinking_prompt(self, available_tools: List[Dict[str, Any]]) -> str:
        """사고 프롬프트 생성"""

        # 이전 관찰 기록 포맷팅
        observations_text = ""
        successful_actions = []  # 성공한 액션 추적 (도구명+파라미터 요약)

        for obs in self.context["observations"][-5:]:  # 최근 5개만
            action = obs['action']
            action_name = f"{action['tool']}.{action['operation']}"
            observation = obs['observation']
            params = action.get('params', {})

            # 성공 여부 판단
            success_indicator = ""
            if "'success': True" in observation or '"success": true' in observation.lower():
                success_indicator = " ✅ SUCCESS"
                # 파라미터 요약 추가 (search_documents의 경우 쿼리 타입 표시)
                param_summary = ""
                if "search_documents" in action_name and params:
                    body = params.get('body', {})
                    query = body.get('query', {})
                    if 'match_all' in query:
                        param_summary = " (match_all)"
                    elif 'match' in query or 'term' in query or 'bool' in query:
                        # 첫 번째 필드명 추출
                        first_key = str(query).split("'")[1] if "'" in str(query) else "filtered"
                        param_summary = f" (query:{first_key})"
                successful_actions.append(f"{action_name}{param_summary}")
            elif "'success': False" in observation or '"success": false' in observation.lower():
                success_indicator = " ❌ FAILED"

            # search_documents 결과는 더 많은 데이터 포함 (로그 분석에 필요)
            if "search_documents" in action_name and success_indicator == " ✅ SUCCESS":
                obs_preview = observation[:1500]  # 1500자까지 (로그 분석용) - 4000에서 줄임
            else:
                obs_preview = observation[:500]  # 일반 결과는 500자 - 800에서 줄임

            # 파라미터 요약도 표시
            param_display = ""
            if params:
                param_str = str(params)[:200]  # 파라미터 200자까지
                param_display = f"\nParams: {param_str}..."

            observations_text += f"\n--- Iteration {obs['iteration']} ---\n"
            observations_text += f"Thought: {obs['thought']}\n"
            observations_text += f"Action: {action_name}{success_indicator}{param_display}\n"
            observations_text += f"Observation: {obs_preview}{'...(more data available)' if len(observation) > len(obs_preview) else ''}\n"

        # 성공한 액션에 대한 경고 추가 (파라미터 요약 포함)
        if successful_actions:
            observations_text += f"\n{'='*60}\n"
            observations_text += f"⛔ STOP! ALREADY DONE: {', '.join(successful_actions)}\n"
            observations_text += f"⛔ DO NOT REPEAT with same params!\n"
            observations_text += f"⛔ Use DIFFERENT query/filter if using same tool!\n"
            observations_text += f"   Good: match_all → event.code:4688 → CommandLine search\n"
            observations_text += f"   Bad:  match_all → match_all (FORBIDDEN!)\n"
            observations_text += f"{'='*60}\n"

        # 도구 정보 포맷팅 - SIEM 관련 도구 우선 표시
        elastic_tools = [t for t in available_tools if t['server'] == 'elastic']
        other_tools = [t for t in available_tools if t['server'] != 'elastic']
        prioritized_tools = elastic_tools + other_tools

        tools_text = ""
        for tool in prioritized_tools[:10]:  # 최대 10개
            tools_text += f"\n- {tool['server']}.{tool['tool_name']}: {tool['description']}\n"
            if tool['input_schema'].get('required'):
                tools_text += f"  Required params: {', '.join(tool['input_schema']['required'])}\n"

        prompt = f"""DFIR 분석 에이전트. 도구를 사용하여 사용자 요청 해결.

**요청:** {self.context['prompt']}

**수집한 정보:**
{observations_text if observations_text else '첫 단계 - 정보 없음'}

**도구:**
{tools_text}

**⚠️ RULES:**

1. **Tool Selection**:
   - For SIEM/log analysis → USE elastic.* tools FIRST
   - For disk/file analysis → USE sleuthkit.* or velociraptor.* tools
   - Check available tools list above!

2. **NO DUPLICATE PARAMS**: Same tool = DIFFERENT query!

3. **SIEM Analysis Flow**:
   1) elastic.list_indices
   2) elastic.search_documents(match_all, size=10)
   3) elastic.search_documents(event.code:4688)
   4) elastic.search_documents(CommandLine filter)
   5) finished:true

**Elasticsearch Query Examples**:
```
{{"index": "demo_2_winlog", "body": {{"query": {{"match_all": {{}}}}, "size": 10}}}}
{{"index": "demo_2_winlog", "body": {{"query": {{"match": {{"event.code": "4688"}}}}, "size": 20}}}}
```

**OUTPUT (JSON only, no markdown):**

Example 1 - First search:
{{
  "thought": "Search SIEM logs from demo_2_winlog index",
  "action": {{
    "tool": "elastic",
    "operation": "search_documents",
    "params": {{
      "index": "demo_2_winlog",
      "body": {{
        "query": {{"match_all": {{}}}},
        "size": 10
      }}
    }}
  }},
  "finished": false
}}

Example 2 - Different query:
{{
  "thought": "Search for process execution events (4688)",
  "action": {{
    "tool": "elastic",
    "operation": "search_documents",
    "params": {{
      "index": "demo_2_winlog",
      "body": {{
        "query": {{"match": {{"event.code": "4688"}}}},
        "size": 20
      }}
    }}
  }},
  "finished": false
}}

Example 3 - Finish:
{{
  "thought": "Collected enough data, providing analysis",
  "finished": true,
  "answer": "Analysis based on observed data: [details]"
}}

IMPORTANT: Output ONLY valid JSON. NO markdown. NO extra text."""

        return prompt

    def _format_observations(self, observations: List[Dict[str, Any]]) -> str:
        """관찰 기록 포맷팅"""
        if not observations:
            return "아직 정보 없음"

        text = ""
        for obs in observations[-5:]:  # 최근 5개만
            text += f"\n{obs['iteration']}. {obs['thought']}\n"
            text += f"   Action: {obs['action']['tool']}.{obs['action']['operation']}\n"
            text += f"   Result: {obs['observation'][:200]}...\n"

        return text

    def _force_analysis_from_observations(self) -> str:
        """반복 감지 시 수집된 데이터로 강제 분석 수행"""
        observations = self.context["observations"]

        # 수집된 데이터 요약
        data_summary = f"**User Request:** {self.context['prompt']}\n\n"
        data_summary += f"**Collected Data ({len(observations)} actions):**\n\n"

        for obs in observations:
            action_name = f"{obs['action']['tool']}.{obs['action']['operation']}"
            # search_documents 결과는 더 자세히
            if "search_documents" in action_name:
                preview_len = 2000
            else:
                preview_len = 500

            data_summary += f"### Action {obs['iteration']}: {action_name}\n"
            data_summary += f"Result: {obs['observation'][:preview_len]}\n\n"

        # LLM에게 분석 요청
        analysis_prompt = f"""You are a DFIR analyst. The agent collected SIEM data but is repeating actions.

Please analyze the collected data and provide a comprehensive SIEM analysis report.

{data_summary}

Provide a detailed analysis including:
1. Total events found
2. Key event details (timestamps, event IDs, processes, etc.)
3. Suspicious patterns or anomalies
4. Potential malicious indicators
5. Recommendations

Be specific and reference actual data from the observations above."""

        try:
            print("\n[Force Analysis] Requesting LLM to analyze collected data...")
            response = self.llm.chat(
                [{"role": "user", "content": analysis_prompt}],
                timeout=60
            )
            analysis = response["choices"][0]["message"]["content"]
            print(f"[Force Analysis] Completed!")
            return analysis
        except Exception as e:
            print(f"[Force Analysis] Failed: {e}")
            return self._generate_summary_from_observations()

    def _generate_summary_from_observations(self) -> str:
        """종료 이유에 따라 관찰 내용으로부터 요약 생성"""
        observations = self.context["observations"]
        termination_reason = self.context.get("termination_reason", "unknown")

        # 종료 이유에 따른 메시지
        if termination_reason == "max_iterations":
            summary = f"최대 반복 횟수({self.max_iterations})에 도달하여 분석이 완료되지 못했습니다.\n\n"
        elif termination_reason == "duplicate_actions":
            summary = f"동일한 작업이 반복되어 강제 종료되었습니다.\n\n"
        elif termination_reason == "no_action":
            summary = f"LLM이 다음 행동을 결정하지 못해 종료되었습니다.\n\n"
        else:
            summary = f"분석이 예상치 못한 이유로 종료되었습니다.\n\n"

        summary += f"**수행된 작업 ({len(observations)}개):**\n"

        for obs in observations[-10:]:  # 마지막 10개만
            action = obs['action']
            result_preview = obs['observation'][:200].replace('\n', ' ')
            summary += f"\n{obs['iteration']}. {action['tool']}.{action['operation']}\n"
            summary += f"   결과: {result_preview}...\n"

        summary += "\n**권장 조치:**\n"
        if termination_reason == "max_iterations":
            summary += "- 프롬프트를 더 구체적으로 수정하세요\n"
            summary += "- 더 강력한 LLM을 사용하거나 Two-Stage 모드를 시도하세요\n"
        elif termination_reason == "duplicate_actions":
            summary += "- LLM이 동일한 쿼리를 반복했습니다. 더 강력한 LLM 사용을 권장합니다\n"
            summary += "- Two-Stage Planning 모드를 시도해보세요\n"
        else:
            summary += "- 프롬프트를 더 구체적으로 수정하세요\n"
            summary += "- 도구 선택이 반복 실패하는 경우 로그를 확인하세요\n"

        return summary
