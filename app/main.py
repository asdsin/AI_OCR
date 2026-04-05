"""
PLC OCR Agent - FastAPI 메인 서버
듀얼 OCR(EasyOCR + PaddleOCR) 기반 PLC 화면 자동 판정 시스템
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.config import settings
from app.database import init_db
from app.services.ocr_engine import ocr_engine
from app.routers import templates, ocr, master, criteria, qr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"🚀 {settings.APP_NAME} v{settings.VERSION} 시작")

    # DB 초기화
    os.makedirs(os.path.dirname(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")), exist_ok=True)
    await init_db()
    logger.info("DB 초기화 완료")

    # OCR 엔진 예열 (첫 요청 대기 시간 줄이기)
    logger.info("OCR 엔진 초기화 중... (첫 실행 시 모델 다운로드)")
    await ocr_engine.initialize()
    logger.info("OCR 엔진 준비 완료")

    yield

    # Shutdown
    logger.info("서버 종료")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="PLC 화면 촬영 → 듀얼 OCR → 자동 판정 에이전트",
    lifespan=lifespan
)

# CORS (프론트엔드 PWA 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 업로드 이미지 정적 서빙
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# 모바일 UI 정적 서빙 (캐시 비활성화)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/app"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

app.add_middleware(NoCacheMiddleware)

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/app", StaticFiles(directory=static_dir, html=True), name="static")

# 라우터 등록
app.include_router(templates.router)
app.include_router(ocr.router)
app.include_router(master.router)
app.include_router(criteria.router)
app.include_router(qr.router)


@app.get("/")
async def root():
    """루트 → 모바일 UI로 리다이렉트"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app/index.html")


@app.get("/api")
async def api_info():
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "running",
        "engines": {
            "primary": settings.OCR_PRIMARY,
            "fallback": settings.OCR_FALLBACK
        },
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "easyocr": ocr_engine._easyocr_reader is not None,
        "paddleocr": ocr_engine._paddleocr_engine is not None
    }
