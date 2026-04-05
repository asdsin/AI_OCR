"""
PLC 화면 유형별 사전 학습 패턴

실제 PLC/HMI 화면에서 자주 나타나는 패턴을 유형별로 정의하여
OCR 결과에서 노이즈를 제거하고 판정 대상 수치를 정확히 식별

참고: LS XGT, Mitsubishi GOT, Siemens SIMATIC 등 주요 제조사 화면 분석 기반
"""
import re
from dataclasses import dataclass


# ═══ PLC 화면 유형 정의 ═══

PLC_SCREEN_TYPES = {
    "current_monitor": {
        "name": "전류 모니터링",
        "description": "히터/모터 전류값 표시 (SCR, 인버터 등)",
        "typical_units": ["A", "mA"],
        "value_range": (0.1, 200),
        "common_labels": ["MAX", "현재", "SV", "PV", "FV", "R상", "S상", "T상"],
        "noise_patterns": [
            r"HEATER", r"SCR", r"MAIN\s*MENU", r"LIST",
            r"#\d+-\d+", r"\d{4}[/\-]\d{2}", r"\d{1,2}\s*:\s*\d{2}",
        ],
    },
    "temperature_monitor": {
        "name": "온도 모니터링",
        "description": "히터/건조기/오븐 온도 표시",
        "typical_units": ["°C", "℃", "C"],
        "value_range": (0, 500),
        "common_labels": ["SV", "PV", "SP", "온도", "TEMP", "설정", "현재", "출력"],
        "noise_patterns": [
            r"HEATER", r"CONTROL", r"PANEL", r"파트별", r"화면",
            r"#\d+-\d+", r"\d{4}[/\-]\d{2}", r"OFF|ON",
        ],
    },
    "pressure_monitor": {
        "name": "압력 모니터링",
        "description": "유압/공압 압력 표시",
        "typical_units": ["MPa", "bar", "kPa", "psi", "kg/cm²"],
        "value_range": (0, 100),
        "common_labels": ["압력", "PRES", "PRESSURE", "설정", "현재"],
        "noise_patterns": [
            r"MAIN", r"MENU", r"ALARM",
            r"#\d+-\d+", r"\d{4}[/\-]\d{2}",
        ],
    },
    "speed_monitor": {
        "name": "속도/회전수 모니터링",
        "description": "모터 RPM, 컨베이어 속도 등",
        "typical_units": ["rpm", "RPM", "m/min", "Hz"],
        "value_range": (0, 5000),
        "common_labels": ["RPM", "속도", "SPEED", "주파수", "FREQ", "설정", "현재"],
        "noise_patterns": [
            r"INVERTER", r"VFD", r"DRIVE",
            r"#\d+-\d+", r"\d{4}[/\-]\d{2}",
        ],
    },
    "general_monitor": {
        "name": "일반 모니터링",
        "description": "범용 PLC 화면",
        "typical_units": [""],
        "value_range": (0, 9999),
        "common_labels": ["SV", "PV", "SP", "설정", "현재", "MAX", "MIN"],
        "noise_patterns": [
            r"MAIN\s*MENU", r"ALARM", r"LIST", r"PANEL",
            r"#\d+-\d+", r"\d{4}[/\-]\d{2}", r"\d{1,2}\s*:\s*\d{2}",
        ],
    },
}


# ═══ 공통 노이즈 패턴 (모든 PLC 화면에서 나타남) ═══

COMMON_NOISE_PATTERNS = [
    # 날짜/시간
    r'\d{4}[/\-]\d{2}[/\-]\d{2}',          # 2026/03/13
    r'\d{1,2}\s*:\s*\d{2}\s*:\s*\d{2}',    # 11:05:00
    r'\d{1,2}\s*:\s*\d{2}',                  # 11:05
    r'\((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\)',   # (Fri)
    # 장비/메뉴 레이블
    r'MAIN\s*MENU',
    r'HEATER\s*화면',
    r'CONTROL\s*PANEL',
    r'설정\s*화면',
    r'알람\s*(?:화면|LIST)',
    r'전류\s*(?:화면|LIST)',
    # 식별자
    r'#\d+-\d+\s*(?:HEATER|히터)',
    r'#[A-Z]?-?\d+',
    # 단위만 단독
    r'^[A-Z]$',
    r'^[RST]상$',
    # 약어 레이블
    r'^(?:SCR|PID|I/O|DI|DO|AI|AO)$',
    # 제조사/모델
    r'(?:LS|LG|SIEMENS|MITSUBISHI|OMRON)',
    r'(?:XGT|GOT|SIMATIC|MELSEC)',
    r'HSPTC',
    r'NIR',
]

# ═══ 공통 수치 레이블 (이것이 근처에 있으면 수치가 판정 대상) ═══

VALUE_CONTEXT_LABELS = [
    "MAX", "MIN", "SV", "PV", "SP", "FV",
    "현재", "설정", "출력", "전류", "온도", "압력", "속도",
    "R상", "S상", "T상",
    "TEMP", "PRES", "SPEED", "CURRENT",
    "히터", "모터", "인버터",
]


def is_noise(text: str, screen_type: str = "general_monitor") -> bool:
    """텍스트가 노이즈인지 판별"""
    text_clean = text.strip()
    if not text_clean or len(text_clean) < 2:
        return True

    # 공통 노이즈
    for pat in COMMON_NOISE_PATTERNS:
        if re.search(pat, text_clean, re.IGNORECASE):
            return True

    # 화면 유형별 노이즈
    screen = PLC_SCREEN_TYPES.get(screen_type, PLC_SCREEN_TYPES["general_monitor"])
    for pat in screen.get("noise_patterns", []):
        if re.search(pat, text_clean, re.IGNORECASE):
            return True

    return False


def classify_value(value: float, text: str, screen_type: str = "general_monitor") -> dict:
    """수치값을 화면 유형에 맞게 분류"""
    screen = PLC_SCREEN_TYPES.get(screen_type, PLC_SCREEN_TYPES["general_monitor"])
    vmin, vmax = screen["value_range"]

    # 범위 밖이면 노이즈 가능성
    if value < vmin or value > vmax:
        return {"valid": False, "reason": f"범위 밖 ({vmin}~{vmax})"}

    # 단위 추출 시도
    unit_match = None
    for unit in screen["typical_units"]:
        if unit and unit.lower() in text.lower():
            unit_match = unit
            break

    return {
        "valid": True,
        "unit": unit_match,
        "screen_type": screen_type,
        "screen_name": screen["name"],
    }


def suggest_screen_type(detected_texts: list[str]) -> str:
    """감지된 텍스트 목록에서 화면 유형 추측"""
    text_joined = " ".join(detected_texts).upper()

    scores = {}
    for stype, sinfo in PLC_SCREEN_TYPES.items():
        score = 0
        for label in sinfo["common_labels"]:
            if label.upper() in text_joined:
                score += 1
        for unit in sinfo["typical_units"]:
            if unit and unit.upper() in text_joined:
                score += 3
        scores[stype] = score

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general_monitor"


# ═══ 제조사별 화면 특성 ═══

MANUFACTURER_PATTERNS = {
    "LS": {
        "identifiers": ["LS", "XGT", "XGB", "XP-Builder"],
        "screen_style": "테이블 그리드, 색상 배경 상태표시, 한글 레이블",
        "typical_resolution": "800x600 ~ 1024x768",
        "color_scheme": {
            "ok": "녹색/청색 배경",
            "warning": "주황/노란색 배경",
            "ng": "빨간/핑크 배경",
        },
    },
    "Mitsubishi": {
        "identifiers": ["MITSUBISHI", "GOT", "MELSEC", "GX Works"],
        "screen_style": "깔끔한 테이블, 수치 중심, 일본어/영어 혼용",
        "typical_resolution": "800x480 ~ 1024x768",
        "color_scheme": {
            "ok": "흰색/연두 배경",
            "warning": "노랑 배경",
            "ng": "빨강 배경",
        },
    },
    "Siemens": {
        "identifiers": ["SIEMENS", "SIMATIC", "WinCC", "S7"],
        "screen_style": "바 그래프, 트렌드 차트, 유럽식 레이아웃",
        "typical_resolution": "1024x768 ~ 1920x1080",
        "color_scheme": {
            "ok": "녹색 바/텍스트",
            "warning": "노란 바/텍스트",
            "ng": "빨간 바/텍스트",
        },
    },
    "LG": {
        "identifiers": ["LG", "HSPTC", "LGIS"],
        "screen_style": "한국식 테이블, 색상 배경, 한글 중심",
        "typical_resolution": "800x600 ~ 1024x768",
        "color_scheme": {
            "ok": "흰색/청색 배경",
            "warning": "노랑 배경",
            "ng": "빨강 배경",
        },
    },
    "Omron": {
        "identifiers": ["OMRON", "NJ", "NX", "NS", "NA"],
        "screen_style": "모던 UI, 그래픽 중심",
        "typical_resolution": "800x480 ~ 1280x800",
        "color_scheme": {
            "ok": "녹색",
            "warning": "주황",
            "ng": "빨강",
        },
    },
}


def detect_manufacturer(detected_texts: list[str]) -> str | None:
    """감지된 텍스트에서 PLC 제조사 추측"""
    text_joined = " ".join(detected_texts).upper()
    for mfr, info in MANUFACTURER_PATTERNS.items():
        for ident in info["identifiers"]:
            if ident.upper() in text_joined:
                return mfr
    return None
