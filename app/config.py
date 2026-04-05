from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    APP_NAME: str = "PLC OCR Agent"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # DB (SQLite for free, upgrade to PostgreSQL later)
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/data/plc_agent.db"

    # OCR (Python 3.14: PaddleOCR 미지원, EasyOCR 기본 + 전처리 변형 Fallback)
    OCR_PRIMARY: str = "easyocr"       # easyocr (기본)
    OCR_FALLBACK: str = "easyocr_enhanced"  # 전처리 강화 후 재시도
    OCR_CONFIDENCE_THRESHOLD: float = 0.5
    OCR_LANGUAGES: list[str] = ["ko", "en"]

    # Image
    UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    MAX_IMAGE_SIZE: int = 10 * 1024 * 1024  # 10MB

    # CORS
    CORS_ORIGINS: list[str] = ["*"]

    class Config:
        env_file = ".env"


settings = Settings()
