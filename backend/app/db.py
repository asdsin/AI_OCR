"""
데이터베이스 연결 설정 — SQLAlchemy + SQLite
DB 파일: backend/data/db/poc_v2.db
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ── DB 파일 경로 ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "data", "db")
DB_PATH = os.path.join(DB_DIR, "poc_v2.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ── 엔진 생성 ──
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 멀티스레드 허용
    echo=False,  # SQL 로그 (디버그 시 True)
)

# ── 세션 팩토리 ──
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── 모델 베이스 클래스 ──
Base = declarative_base()


def get_db():
    """FastAPI 의존성 주입용 DB 세션 제공 함수"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """테이블 자동 생성 — 서버 시작 시 호출"""
    os.makedirs(DB_DIR, exist_ok=True)
    Base.metadata.create_all(bind=engine)
