"""Placeholder 해석기 모듈

이전 단계 실행 결과에서 값을 추출하여 PLACEHOLDER 치환
예: PLACEHOLDER_CLIENT_ID → 실제 client_id 값
"""
from __future__ import annotations
import json
import re
from typing import Dict, Any, List

class PlaceholderResolver:
    """Placeholder 값을 실제 값으로 치환하는 클래스"""

    @staticmethod

    def resolve(params: Dict[str, Any], results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """파라미터에서 PLACEHOLDER를 찾아 실제 값으로 치환

        Args:
            params: 현재 액션의 파라미터 (PLACEHOLDER 포함 가능)
            results: 이전 실행 결과 리스트

        Returns:
            Dict[str, Any]: 치환된 파라미터 딕셔너리
        """
        resolved_params = params.copy()

        if "fs_offset_sectors" in resolved_params and resolved_params["fs_offset_sectors"] is None:
            print(f"  ⚠️  fs_offset_sectors가 None입니다. PLACEHOLDER_OFFSET으로 자동 치환합니다.")
            resolved_params["fs_offset_sectors"] = "PLACEHOLDER_OFFSET"

        if "inodes" in resolved_params and resolved_params["inodes"] is None:
            print(f"  ⚠️  inodes가 None입니다. PLACEHOLDER_INODES로 자동 치환합니다.")
            resolved_params["inodes"] = "PLACEHOLDER_INODES"

        if not results or "PLACEHOLDER_" not in str(resolved_params):
            return resolved_params

        if "PLACEHOLDER_OFFSET" in str(params):
            resolved_params = PlaceholderResolver._resolve_offset(resolved_params, results)

        if "PLACEHOLDER_CLIENT_ID" in str(params):
            resolved_params = PlaceholderResolver._resolve_client_id(resolved_params, results)

        if results and len(results) > 0:
            prev_result = results[-1]

            if prev_result.get("success"):
                resolved_params = PlaceholderResolver._resolve_from_result(
                    resolved_params, prev_result
                )
            else:
                if "PLACEHOLDER_INODES" in str(resolved_params):
                    print(f"  ⚠️  이전 단계 실패로 inodes를 추출할 수 없습니다. 빈 리스트로 치환하고 실행을 건너뜁니다.")
                    resolved_params = PlaceholderResolver._replace_placeholder(
                        resolved_params, "PLACEHOLDER_INODES", []
                    )
                    resolved_params["_skip_execution"] = True

        return resolved_params

    @staticmethod
    def _resolve_client_id(params: Dict[str, Any], results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """PLACEHOLDER_CLIENT_ID 처리: 모든 이전 결과에서 client_id 찾기

        Args:
            params: 파라미터
            results: 실행 결과 리스트

        Returns:
            치환된 파라미터
        """
        for result in reversed(results):
            if not result.get("success"):
                continue

            try:
                result_data = result.get("result", "{}")

                if isinstance(result_data, str):
                    result_json = json.loads(result_data)
                else:
                    result_json = result_data

                if isinstance(result_json, dict):
                    client_id = result_json.get("client_id", "")

                    if client_id:
                        params = PlaceholderResolver._replace_placeholder(
                            params, "PLACEHOLDER_CLIENT_ID", client_id
                        )
                        print(f"  ℹ️  client_id 추출 완료: {client_id}")
                        return params

            except (json.JSONDecodeError, AttributeError):
                continue

        print(f"  ⚠️  이전 결과에서 client_id를 찾을 수 없습니다")
        return params

    @staticmethod

    def _resolve_offset(params: Dict[str, Any], results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """PLACEHOLDER_OFFSET 처리: 디스크 파티션 정보에서 오프셋 추출

        Args:
            params: 파라미터
            results: 실행 결과 리스트

        Returns:
            치환된 파라미터
        """
        if not results:
            print("  ⚠️  결과가 없어 오프셋을 추출할 수 없음, 기본값 2048 사용")

            return PlaceholderResolver._replace_placeholder(params, "PLACEHOLDER_OFFSET", "2048")
        first_result = results[0]

        if not first_result.get("success"):
            print("  ⚠️  첫 번째 결과가 실패, 기본값 2048 사용")

            return PlaceholderResolver._replace_placeholder(params, "PLACEHOLDER_OFFSET", "2048")

        try:
            result_data = first_result.get("result", "{}")

            if isinstance(result_data, str):
                result_json = json.loads(result_data)

            else:
                result_json = result_data
            stdout = result_json.get("stdout", "")
            partition_match = re.search(
                r'\d+:\s+\d+\s+(\d+)\s+\d+\s+\d+\s+Basic data partition',
                stdout
            )

            if partition_match:
                offset = partition_match.group(1).lstrip('0') or '0'
                print(f"  ℹ️  파티션 오프셋 추출 완료: {offset}")

                return PlaceholderResolver._replace_placeholder(params, "PLACEHOLDER_OFFSET", offset)

            else:
                print(f"  ⚠️  파티션 오프셋을 찾을 수 없음, 기본값 2048 사용")

                return PlaceholderResolver._replace_placeholder(params, "PLACEHOLDER_OFFSET", "2048")

        except (json.JSONDecodeError, AttributeError) as e:
            print(f"  ⚠️  오프셋 파싱 실패: {e}, 기본값 2048 사용")

            return PlaceholderResolver._replace_placeholder(params, "PLACEHOLDER_OFFSET", "2048")

    @staticmethod

    def _resolve_from_result(
        params: Dict[str, Any],
        prev_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """가장 최근 결과에서 PLACEHOLDER 값 추출

        Args:
            params: 파라미터
            prev_result: 이전 실행 결과

        Returns:
            치환된 파라미터
        """
        try:
            result_data = prev_result.get("result", "{}")

            if isinstance(result_data, str):
                try:
                    result_json = json.loads(result_data)
                except json.JSONDecodeError:
                    result_json = result_data
            else:
                result_json = result_data

            if not isinstance(result_json, dict):
                if "PLACEHOLDER_INDEX" in str(params):
                    index_name = PlaceholderResolver._extract_first_index(result_json)
                    if index_name:
                        params = PlaceholderResolver._replace_placeholder(
                            params, "PLACEHOLDER_INDEX", index_name
                        )
                        print(f"     index 추출 완료: {index_name}")
                    else:
                        print(f"     이전 결과에서 인덱스를 찾을 수 없습니다 (결과 타입: {type(result_json).__name__})")
                # else: 조용히 무시 (client_id는 _resolve_client_id에서 처리됨)
                return params

            if "PLACEHOLDER_INODES" in str(params):
                inodes = result_json.get("inodes", [])

                if inodes and len(inodes) > 0:
                    if isinstance(inodes, list) and any("not found" in str(inode).lower() or "error" in str(inode).lower() for inode in inodes):
                        print(f"  ❌ inode 검색 실패: {inodes}")
                        print(f"  ❌ 파일 추출을 진행할 수 없습니다. 다음 단계를 건너뜁니다.")
                        params["_skip_execution"] = True
                        params = PlaceholderResolver._replace_placeholder(
                            params, "PLACEHOLDER_INODES", []
                        )
                    else:
                        params = PlaceholderResolver._replace_placeholder(
                            params, "PLACEHOLDER_INODES", inodes
                        )
                        print(f"  ℹ️  inodes 추출 완료: {inodes}")

                else:
                    params = PlaceholderResolver._replace_placeholder(
                        params, "PLACEHOLDER_INODES", []
                    )
                    print(f"  ⚠️  이전 결과에 inodes가 없습니다 (빈 리스트 사용)")
                    params["_skip_execution"] = True

            if "PLACEHOLDER_INDEX" in str(params):
                index_name = PlaceholderResolver._extract_first_index(result_json)

                if index_name:
                    params = PlaceholderResolver._replace_placeholder(
                        params, "PLACEHOLDER_INDEX", index_name
                    )
                    print(f"  ℹ️  index 추출 완료: {index_name}")

                else:
                    print(f"  ⚠️  이전 결과에서 인덱스를 찾을 수 없습니다")

            return params

        except (json.JSONDecodeError, AttributeError) as e:
            print(f"  ⚠️  이전 결과 파싱 실패: {e}")

            return params

    @staticmethod

    def _extract_first_index(result_json: Dict[str, Any]) -> str:
        """list_indices 결과에서 첫 번째 인덱스명 추출

        Args:
            result_json: list_indices 실행 결과

        Returns:
            인덱스명 또는 빈 문자열
        """
        try:

            if isinstance(result_json, list) and len(result_json) > 0:

                for item in result_json:

                    if isinstance(item, dict) and "index" in item:
                        index_name = item["index"]

                        if not index_name.startswith("."):
                            doc_count = item.get("docs.count", item.get("docs_count", 1))

                            if doc_count and int(doc_count) > 0:

                                return index_name

                for item in result_json:

                    if isinstance(item, dict) and "index" in item:
                        index_name = item["index"]

                        if not index_name.startswith("."):

                            return index_name

            if isinstance(result_json, str):

                try:
                    parsed = json.loads(result_json)

                    if isinstance(parsed, list) and len(parsed) > 0:

                        return PlaceholderResolver._extract_first_index(parsed)

                except json.JSONDecodeError:
                    lines = result_json.strip().split('\n')

                    for line in lines:
                        parts = line.strip().split()

                        if len(parts) >= 7:
                            index_name = parts[2]
                            doc_count = parts[6]

                            if not index_name.startswith(".") and doc_count.isdigit() and int(doc_count) > 0:
                                print(f"  ℹ️  _cat/indices 형식에서 인덱스 추출: {index_name} (문서: {doc_count}개)")

                                return index_name

                    for line in lines:
                        parts = line.strip().split()

                        if len(parts) >= 3:
                            index_name = parts[2]

                            if not index_name.startswith("."):
                                print(f"  ℹ️  _cat/indices 형식에서 인덱스 추출: {index_name} (문서 개수 무시)")

                                return index_name

            return ""

        except Exception as e:
            print(f"  ⚠️  인덱스 추출 중 오류: {e}")

            return ""

    @staticmethod

    def _replace_placeholder(
        params: Dict[str, Any],
        placeholder: str,
        value: Any
    ) -> Dict[str, Any]:
        """딕셔너리에서 placeholder를 value로 치환

        Args:
            params: 파라미터 딕셔너리
            placeholder: 치환할 placeholder 문자열
            value: 치환할 값

        Returns:
            치환된 파라미터
        """
        return {
            k: (value if v == placeholder else v)

            for k, v in params.items()
        }

