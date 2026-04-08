# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PLC OCR Agent — PLC/HMI 화면을 스마트폰으로 촬영하여 수치를 자동 인식하고 OK/NG 판정하는 시스템. (주)위즈팩토리의 제조공정 데이터 수집 도구.

## Commands

```bash
# 서버 시작 (HTTP :8001)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# HTTP + HTTPS 동시 (카메라용 HTTPS :8443)
python run.py

# HTTPS 인증서 생성 (최초 1회)
python gen_cert.py

# 데모 데이터 투입 (서버 실행 중 별도 터미널)
python seed.py

# PaddleOCR 테스트 (Python 3.11 venv 사용)
venv311/Scripts/python -c "from paddleocr import PaddleOCR; print('OK')"
```

## Architecture

### Dual Python Runtime
- **메인 서버**: Python 3.14 (FastAPI + EasyOCR + Tesseract)
- **PaddleOCR**: Python 3.11 가상환경(`venv311/`) — `paddle_bridge.py`가 subprocess로 호출
- PaddleOCR는 Python 3.14를 지원하지 않으므로 이 구조가 필수

### OCR Engine Pipeline (multi_engine_ocr.py)
```
이미지 → 3가지 전처리(원본/이진화/반전)
  ├── EasyOCR × 3 = 3후보
  ├── Tesseract × 3 = 3후보
  └── PaddleOCR × 1 = 2후보 (가중 투표)
총 8후보 → 다수결 투표 → applyFormat(자릿수 필터) → 최종값
```

### Data Hierarchy
```
Company → Division → ProductionLine → Process → Equipment → QrPoint
                                                              ↓
                                                    profile_data (JSON)
                                                    = 영역좌표 + 포맷 + 판정조건
```
- `QrPoint`가 판정의 단위. 하나의 Equipment에 여러 QrPoint(화면별)
- 판정 프로필은 `QrPoint.profile_data` JSON 필드에 저장
- 로컬에도 `localStorage`에 `profile_{qrCode}` 키로 백업

### Frontend (static/index.html)
단일 HTML 파일. 4탭 구조:
1. **위치**: 카드형 리스트 + 가로 필터 (업체/사업부/라인)
2. **기준설정**: 4단계 위저드 (촬영→영역→항목→조건)
3. **판정**: QR스캔(jsQR) → 카메라촬영 → 멀티엔진OCR → 판정
4. **결과**: 영역별 크롭이미지 + 인식값 + 판정 카드

API 호출은 `location.origin` 기준 (같은 서버에서 서빙).

### Key Services
| File | Role |
|------|------|
| `smart_ocr.py` | 전체화면 OCR (EasyOCR + 최적 파라미터) |
| `multi_engine_ocr.py` | 영역별 멀티엔진 OCR (EasyOCR+Tesseract+PaddleOCR 다수결) |
| `paddle_bridge.py` | PaddleOCR subprocess 브릿지 (venv311) |
| `precision_ocr.py` | 3중 전처리 × 다수결 (단일 영역용) |
| `screen_detector.py` | 촬영 이미지에서 PLC 화면 자동 감지 (베젤 제거) |
| `plc_patterns.py` | PLC 화면 유형별 노이즈 필터 + 제조사 패턴 |
| `judgment_engine.py` | 수치/신호/색상 판정 로직 |
| `qr_print.py` | QR 라벨 이미지 생성 (Pillow) |

### Critical Design Decisions
- **포맷 기반 OCR 필터**: 영역에 "숫자 3자리" 등 포맷을 지정하면 OCR 결과에서 자릿수만 추출 (1312→131). `applyFormat()` 함수 (index.html 내)
- **`<\/script>` 이스케이프**: `document.write()` 안에서 `</script>` 문자열은 `</scr`+`ipt>`로 분할 필수 (브라우저가 메인 스크립트를 조기 종료)
- **한글 경로 문제**: `cv2.imread()`가 한글 경로를 못 읽음 → `np.frombuffer` + `cv2.imdecode` 사용. PaddleOCR 캐시는 `C:/paddleocr_cache`(ASCII 경로)
- **HTTPS 필수 (카메라)**: 스마트폰 `getUserMedia`는 HTTPS에서만 동작. `gen_cert.py`로 자체서명 인증서 생성, :8443에서 서빙

### Database
SQLite (`data/plc_agent.db`), async via `aiosqlite`. 서버 시작 시 `Base.metadata.create_all`로 자동 생성. 13개 테이블:
- 계층: companies, divisions, production_lines, processes, equipments, qr_points
- PLC: plc_templates, ocr_zones
- 판정: judgment_criteria, judgment_history, judgment_corrections, ocr_corrections, accuracy_stats
