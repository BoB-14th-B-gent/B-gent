from fastapi import APIRouter

router = APIRouter()

@router.post("/input", summary="전처리기 증거 업로드")
def upload_preprocessor_evidence():
    return

@router.get("/input/{evidence_id}", summary="전처리기 증거 상세 조회")
def get_preprocessor_evidence():
    return

@router.get("", summary="전체 증거 목록 조회")
def get_evidences():
    return