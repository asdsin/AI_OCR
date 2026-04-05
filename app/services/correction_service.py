"""
보정 학습 서비스 - OCR 오인식 보정 데이터 관리
기존 PoC의 localStorage 보정 로직을 서버로 이전
"""
import re
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import OcrCorrection

logger = logging.getLogger(__name__)


class CorrectionService:

    async def find_correction(self, db: AsyncSession, equipment_id: str,
                              zone_id: str, ocr_text: str) -> OcrCorrection | None:
        """
        기존 보정 데이터에서 매칭되는 보정값 검색
        3단계 매칭: 정확 → 부분포함 → 수치동일
        """
        stmt = select(OcrCorrection).where(
            OcrCorrection.equipment_id == equipment_id,
            OcrCorrection.zone_id == zone_id
        ).order_by(OcrCorrection.applied_count.desc())

        result = await db.execute(stmt)
        candidates = result.scalars().all()

        if not candidates:
            return None

        ocr_norm = re.sub(r'\s+', '', ocr_text).lower()

        for c in candidates:
            c_norm = re.sub(r'\s+', '', c.ocr_text or '').lower()

            # 1. 정확 매칭
            if ocr_norm == c_norm:
                return c

            # 2. 부분 포함
            if ocr_norm and c_norm and (ocr_norm in c_norm or c_norm in ocr_norm):
                return c

            # 3. 수치 동일
            c_nums = re.findall(r'-?\d+\.?\d*', c.ocr_text or '')
            t_nums = re.findall(r'-?\d+\.?\d*', ocr_text)
            if c_nums and t_nums and c_nums[0] == t_nums[0]:
                return c

        return None

    async def apply_correction(self, db: AsyncSession, correction: OcrCorrection) -> None:
        """보정 적용 카운트 증가"""
        correction.applied_count += 1
        await db.commit()

    async def save_correction(self, db: AsyncSession, equipment_id: str,
                              zone_id: str, ocr_text: str, ocr_value: float | None,
                              correct_value: float | None, correct_text: str | None,
                              image_crop_path: str | None = None,
                              created_by: str | None = None) -> OcrCorrection:
        """새 보정 데이터 저장"""
        correction = OcrCorrection(
            equipment_id=equipment_id,
            zone_id=zone_id,
            ocr_text=ocr_text,
            ocr_value=ocr_value,
            correct_value=correct_value,
            correct_text=correct_text,
            image_crop_path=image_crop_path,
            created_by=created_by
        )
        db.add(correction)
        await db.commit()
        await db.refresh(correction)
        logger.info(f"보정 저장: equip={equipment_id}, zone={zone_id}, "
                    f"OCR='{ocr_text}' → correct={correct_value}")
        return correction

    async def get_stats(self, db: AsyncSession, equipment_id: str | None = None) -> dict:
        """보정 통계"""
        stmt = select(OcrCorrection)
        if equipment_id:
            stmt = stmt.where(OcrCorrection.equipment_id == equipment_id)
        result = await db.execute(stmt)
        corrections = result.scalars().all()

        total = len(corrections)
        total_applied = sum(c.applied_count for c in corrections)
        return {
            "total_corrections": total,
            "total_applied": total_applied,
            "avg_applied": total_applied / total if total > 0 else 0
        }


correction_service = CorrectionService()
