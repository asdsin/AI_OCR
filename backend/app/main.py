"""
AI 인식 PoC v2 — FastAPI 메인 서버
PLC 화면 촬영 → OCR → OK/NG 판정 시스템 (폐쇄망 대응)
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ── 로깅 설정 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ── 경로 상수 ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
IMAGE_DIR = os.path.join(DATA_DIR, "images")
DB_DIR = os.path.join(DATA_DIR, "db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행되는 라이프사이클"""
    # ── 시작 ──
    # 데이터 디렉터리 자동 생성
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(DB_DIR, exist_ok=True)
    logger.info("=" * 50)
    logger.info("AI 인식 PoC v2 서버 시작")
    logger.info(f"  데이터 경로: {DATA_DIR}")
    logger.info(f"  이미지 경로: {IMAGE_DIR}")
    logger.info("=" * 50)
    yield
    # ── 종료 ──
    logger.info("서버 종료")


# ── FastAPI 앱 생성 ──
app = FastAPI(
    title="AI 인식 PoC v2",
    version="0.1.0",
    description="PLC 화면 촬영 → OCR → OK/NG 판정 (폐쇄망 대응)",
    lifespan=lifespan,
)

# ── CORS 설정 (프론트엔드에서 호출 가능하도록) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 폐쇄망이므로 전체 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 정적 파일 서빙 (이미지) ──
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")


# ── 헬스체크 엔드포인트 ──
@app.get("/health", tags=["시스템"])
async def health_check():
    """서버 상태 확인용 엔드포인트"""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "message": "AI 인식 PoC v2 정상 동작 중",
    }
