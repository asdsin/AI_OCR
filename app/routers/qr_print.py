"""QR 코드 생성 + 인쇄용 라벨 API"""
import io
import base64
import qrcode
from PIL import Image, ImageDraw, ImageFont
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import QrPoint, Equipment, Process, ProductionLine, Division, Company

router = APIRouter(prefix="/api/qr", tags=["qr-print"])


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    """텍스트를 최대 폭에 맞게 줄바꿈"""
    words = text.replace(' > ', ' > ').split(' ')
    lines, current = [], ''
    for w in words:
        test = (current + ' ' + w).strip() if current else w
        try:
            tw = font.getlength(test)
        except AttributeError:
            tw = len(test) * 8  # fallback
        if tw <= max_width:
            current = test
        else:
            if current: lines.append(current)
            current = w
    if current: lines.append(current)
    return lines or [text]


def _make_qr_image(data: str, box_size: int = 10) -> Image.Image:
    """QR 코드 이미지 생성"""
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=box_size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _make_label(qr_code: str, equip_name: str, screen_name: str,
                path: str, size: str = "medium") -> Image.Image:
    """
    인쇄용 QR 라벨 생성
    size: small(40x25mm), medium(60x40mm), large(80x50mm)
    """
    sizes = {
        "small":  {"w": 480, "h": 300, "qr_box": 6,  "font_lg": 20, "font_md": 16, "font_sm": 12},
        "medium": {"w": 720, "h": 480, "qr_box": 8,  "font_lg": 28, "font_md": 20, "font_sm": 14},
        "large":  {"w": 960, "h": 600, "qr_box": 10, "font_lg": 36, "font_md": 26, "font_sm": 18},
    }
    s = sizes.get(size, sizes["medium"])

    # 라벨 배경 (흰색)
    img = Image.new("RGB", (s["w"], s["h"]), "white")
    draw = ImageDraw.Draw(img)

    # QR 코드 생성
    qr_img = _make_qr_image(qr_code, box_size=s["qr_box"])
    qr_size = min(s["h"] - 40, s["w"] // 2 - 20)
    qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)

    # QR 배치 (왼쪽)
    qr_x, qr_y = 20, (s["h"] - qr_size) // 2
    img.paste(qr_img, (qr_x, qr_y))

    # 텍스트 영역 (오른쪽)
    tx = qr_x + qr_size + 20
    ty = 20

    # 폰트 (시스템 기본)
    try:
        font_lg = ImageFont.truetype("malgun.ttf", s["font_lg"])
        font_md = ImageFont.truetype("malgun.ttf", s["font_md"])
        font_sm = ImageFont.truetype("malgun.ttf", s["font_sm"])
    except (OSError, IOError):
        try:
            font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s["font_lg"])
            font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", s["font_md"])
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", s["font_sm"])
        except (OSError, IOError):
            font_lg = ImageFont.load_default()
            font_md = ImageFont.load_default()
            font_sm = ImageFont.load_default()

    max_w = s["w"] - tx - 10

    # 설비명 (굵게)
    draw.text((tx, ty), equip_name, fill="black", font=font_lg)
    ty += s["font_lg"] + 8

    # 화면명
    draw.text((tx, ty), screen_name, fill="#333333", font=font_md)
    ty += s["font_md"] + 6

    # 구분선
    draw.line([(tx, ty), (s["w"] - 10, ty)], fill="#cccccc", width=1)
    ty += 8

    # 경로 (자동 줄바꿈)
    for line in _wrap_text(path, font_sm, max_w):
        draw.text((tx, ty), line, fill="#666666", font=font_sm)
        ty += s["font_sm"] + 2

    ty += 4
    # QR 코드값
    draw.text((tx, ty), f"QR: {qr_code}", fill="#999999", font=font_sm)
    ty += s["font_sm"] + 8

    # 하단 안내
    draw.text((tx, ty), "PLC OCR Agent", fill="#aaaaaa", font=font_sm)

    # 테두리
    draw.rectangle([(0, 0), (s["w"]-1, s["h"]-1)], outline="#cccccc", width=1)
    # 절취선 (점선 효과)
    for x in range(0, s["w"], 8):
        draw.point((x, 0), fill="#999999")
        draw.point((x, s["h"]-1), fill="#999999")

    return img


async def _build_path(db: AsyncSession, equipment_id: str) -> str:
    """설비 → 전체 경로 문자열"""
    eq = await db.get(Equipment, equipment_id)
    if not eq: return ""
    parts = []
    if eq.process_id:
        proc = await db.get(Process, eq.process_id)
        if proc and proc.line_id:
            line = await db.get(ProductionLine, proc.line_id)
            if line and line.division_id:
                div = await db.get(Division, line.division_id)
                if div and div.company_id:
                    comp = await db.get(Company, div.company_id)
                    if comp: parts.append(comp.name)
                parts.append(div.name)
            parts.append(line.name)
        parts.append(proc.name)
    parts.append(eq.name)
    return " > ".join(parts)


# ── 단일 QR 라벨 이미지 ──

@router.get("/label/{qr_point_id}")
async def get_qr_label(
    qr_point_id: str,
    size: str = Query("medium", pattern="^(small|medium|large)$"),
    db: AsyncSession = Depends(get_db)
):
    """QR 포인트의 인쇄용 라벨 이미지 반환 (PNG)"""
    qp = await db.get(QrPoint, qr_point_id)
    if not qp: raise HTTPException(404, "QR 포인트를 찾을 수 없습니다")

    eq = await db.get(Equipment, qp.equipment_id) if qp.equipment_id else None
    path = await _build_path(db, qp.equipment_id) if qp.equipment_id else ""

    label = _make_label(
        qr_code=qp.qr_code,
        equip_name=eq.name if eq else "Unknown",
        screen_name=qp.screen_name,
        path=path,
        size=size,
    )

    buf = io.BytesIO()
    label.save(buf, format="PNG", dpi=(300, 300))
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png",
                             headers={"Content-Disposition": f'inline; filename="qr_{qp.qr_code}.png"'})


# ── 설비의 전체 QR 일괄 출력 (A4 시트) ──

@router.get("/sheet/{equipment_id}")
async def get_qr_sheet(
    equipment_id: str,
    size: str = Query("medium", pattern="^(small|medium|large)$"),
    db: AsyncSession = Depends(get_db)
):
    """설비에 등록된 모든 QR 포인트를 A4 한 장에 배치한 인쇄용 시트"""
    stmt = select(QrPoint).where(
        QrPoint.equipment_id == equipment_id, QrPoint.is_active == True
    )
    qr_points = (await db.execute(stmt)).scalars().all()
    if not qr_points:
        raise HTTPException(404, "등록된 QR 포인트가 없습니다")

    eq = await db.get(Equipment, equipment_id)
    path = await _build_path(db, equipment_id) if equipment_id else ""

    # A4 크기 (300dpi 기준: 2480x3508)
    a4_w, a4_h = 2480, 3508
    sheet = Image.new("RGB", (a4_w, a4_h), "white")
    draw = ImageDraw.Draw(sheet)

    # 헤더
    try:
        font_title = ImageFont.truetype("malgun.ttf", 48)
        font_sub = ImageFont.truetype("malgun.ttf", 28)
    except (OSError, IOError):
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((80, 60), f"QR 라벨 시트 — {eq.name if eq else '설비'}", fill="black", font=font_title)
    draw.text((80, 120), path, fill="#666666", font=font_sub)
    draw.line([(80, 170), (a4_w - 80, 170)], fill="#cccccc", width=2)

    # 라벨 배치 (그리드)
    sizes = {"small": (480, 300), "medium": (720, 480), "large": (960, 600)}
    lw, lh = sizes.get(size, sizes["medium"])
    cols = max(1, (a4_w - 160) // (lw + 20))
    start_y = 200
    x, y = 80, start_y

    for qp in qr_points:
        label = _make_label(
            qr_code=qp.qr_code,
            equip_name=eq.name if eq else "Unknown",
            screen_name=qp.screen_name,
            path=path,
            size=size,
        )
        sheet.paste(label, (x, y))

        x += lw + 20
        if x + lw > a4_w - 80:
            x = 80
            y += lh + 20

    buf = io.BytesIO()
    sheet.save(buf, format="PNG", dpi=(300, 300))
    buf.seek(0)
    equip_code = eq.code if eq else "unknown"
    return StreamingResponse(buf, media_type="image/png",
                             headers={"Content-Disposition": f'inline; filename="qr_sheet_{equip_code}.png"'})


# ── QR 코드만 (base64) ──

@router.get("/qrcode/{qr_code}")
async def get_qr_image(qr_code: str, box_size: int = Query(10, ge=4, le=20)):
    """순수 QR 코드 이미지만 반환"""
    qr_img = _make_qr_image(qr_code, box_size=box_size)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
