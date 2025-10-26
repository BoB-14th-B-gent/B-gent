#!/usr/bin/env python3
"""MCP_EVIDENCES 컬렉션에 대한 MongoDB 인덱스 설정

MCP 실행 이력 조회 성능 향상을 위한 인덱스 생성
"""
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from pymongo import ASCENDING, DESCENDING
from core.agent.storage.job_storage import _get_client


def create_mcp_indexes():
    """MCP_EVIDENCES 컬렉션 인덱스 생성

    생성되는 인덱스:
        1. mcp_name (ASCENDING): MCP 서버별 빠른 조회
        2. timestamp (DESCENDING): 시간순 정렬
        3. success (ASCENDING): 성공/실패별 필터링
        4. stage (ASCENDING): 스테이지별 조회

    Returns:
        bool: 인덱스 생성 성공 여부
    """
    try:
        db = _get_client()
        if db is None:
            print("⚠️  MongoDB 연결 실패 - 인덱스를 생성할 수 없습니다")
            return False

        collection = db.MCP_EVIDENCES

        # 기존 인덱스 확인
        existing_indexes = collection.index_information()
        print(f"기존 인덱스: {list(existing_indexes.keys())}")

        # 1. MCP 이름으로 빠른 조회
        index_name = collection.create_index(
            [("mcp_name", ASCENDING)],
            name="idx_mcp_name"
        )
        print(f"✓ 인덱스 생성: {index_name}")

        # 2. 시간순 정렬
        index_name = collection.create_index(
            [("timestamp", DESCENDING)],
            name="idx_timestamp"
        )
        print(f"✓ 인덱스 생성: {index_name}")

        # 3. 성공/실패 필터링
        index_name = collection.create_index(
            [("success", ASCENDING)],
            name="idx_success"
        )
        print(f"✓ 인덱스 생성: {index_name}")

        # 4. 스테이지별 조회
        index_name = collection.create_index(
            [("stage", ASCENDING)],
            name="idx_stage"
        )
        print(f"✓ 인덱스 생성: {index_name}")

        # 5. 복합 인덱스: MCP 이름 + 시간순
        index_name = collection.create_index(
            [("mcp_name", ASCENDING), ("timestamp", DESCENDING)],
            name="idx_mcp_name_timestamp"
        )
        print(f"✓ 인덱스 생성: {index_name}")

        print("\n✅ MongoDB 인덱스 생성 완료!")
        print(f"컬렉션: {collection.name}")

        # 인덱스 목록 출력
        print("\n생성된 인덱스 목록:")
        for idx_name, idx_info in collection.index_information().items():
            print(f"  - {idx_name}: {idx_info.get('key', [])}")

        return True

    except Exception as e:
        print(f"❌ MongoDB 인덱스 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def drop_mcp_indexes():
    """MCP_EVIDENCES 인덱스 삭제

    Warning:
        이 작업은 조회 성능에 영향을 줄 수 있습니다!

    Returns:
        bool: 인덱스 삭제 성공 여부
    """
    try:
        db = _get_client()
        if db is None:
            print("⚠️  MongoDB 연결 실패")
            return False

        collection = db.MCP_EVIDENCES

        # _id 인덱스를 제외한 모든 인덱스 삭제
        collection.drop_indexes()
        print("✓ MCP_EVIDENCES 인덱스 삭제 완료")

        return True

    except Exception as e:
        print(f"⚠️  인덱스 삭제 실패: {e}")
        return False


def show_mcp_indexes():
    """현재 생성된 인덱스 목록 출력

    Returns:
        dict: 인덱스 정보
    """
    try:
        db = _get_client()
        if db is None:
            print("⚠️  MongoDB 연결 실패")
            return {}

        collection = db.MCP_EVIDENCES
        indexes = collection.index_information()

        print(f"\n=== {collection.name} 컬렉션 인덱스 ===")
        for idx_name, idx_info in indexes.items():
            key = idx_info.get('key', [])
            unique = idx_info.get('unique', False)
            print(f"\n인덱스: {idx_name}")
            print(f"  필드: {key}")
            print(f"  고유: {unique}")

        return indexes

    except Exception as e:
        print(f"⚠️  인덱스 조회 실패: {e}")
        return {}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "create":
            create_mcp_indexes()
        elif command == "drop":
            print("⚠️  주의: 모든 인덱스를 삭제하면 조회 성능이 저하됩니다!")
            confirm = input("정말 삭제하시겠습니까? (yes/no): ")
            if confirm.lower() == "yes":
                drop_mcp_indexes()
            else:
                print("취소되었습니다")
        elif command == "show":
            show_mcp_indexes()
        else:
            print(f"알 수 없는 명령: {command}")
            print("사용법: python setup_mcp_indexes.py [create|drop|show]")
    else:
        # 기본 동작: 인덱스 생성
        create_mcp_indexes()
