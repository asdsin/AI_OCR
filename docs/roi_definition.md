# ROI 정의표 템플릿

> 설비별 판독 영역(ROI, Region of Interest)을 정의합니다.
> 이 표의 데이터는 DB의 `inspection_templates` 테이블에 저장됩니다.
> ROI 좌표는 **기준 사진(화면 감지 후) 대비 % 값**입니다.

---

## 컬럼 정의

| 컬럼 | 타입 | 설명 | 예시 |
|------|------|------|------|
| 설비코드 | FK | 설비 목록표의 설비코드 | EQ-A01-001 |
| 템플릿명 | text | 이 ROI가 읽는 항목 이름 | #1-2 히터 온도 PV |
| 판정타입 | enum | numeric / signal / color | numeric |
| ROI_X | float | 좌상단 X 좌표 (%, 0~100) | 13.5 |
| ROI_Y | float | 좌상단 Y 좌표 (%, 0~100) | 26.0 |
| ROI_Width | float | 영역 너비 (%, 0~100) | 10.0 |
| ROI_Height | float | 영역 높이 (%, 0~100) | 6.0 |
| 자릿수 | int | 숫자 자릿수 (수치형만) | 3 |
| 소수점 | bool | 소수점 포함 여부 | ❌ |
| 전처리방식 | text | 이미지 전처리 힌트 | grayscale+threshold |
| 비고 | text | 특이사항 | 검은 배경 흰 글자 |

---

## ROI 정의 (샘플)

| 설비코드 | 템플릿명 | 판정타입 | ROI_X | ROI_Y | ROI_W | ROI_H | 자릿수 | 소수점 | 전처리방식 | 비고 |
|---------|---------|---------|-------|-------|-------|-------|--------|--------|----------|------|
| EQ-A01-001 | #1-2 히터 온도 PV | numeric | 13.5 | 26.0 | 10.0 | 6.0 | 3 | ❌ | grayscale+threshold | 파란 배경 검정 글자 |
| EQ-A01-001 | #2-2 히터 온도 PV | numeric | 35.0 | 26.0 | 10.0 | 6.0 | 3 | ❌ | grayscale+threshold | 파란 배경 검정 글자 |
| EQ-A01-001 | #3-2 히터 온도 PV | numeric | 56.5 | 26.0 | 10.0 | 6.0 | 3 | ❌ | grayscale+threshold | 주황 배경일 때 경고 |

---

## 좌표 체계

```
(0,0) ────────────────────── (100,0)
  │                              │
  │    (ROI_X, ROI_Y)            │
  │      ┌──────────┐            │
  │      │  PV 168  │ ROI_H      │
  │      └──────────┘            │
  │        ROI_W                 │
  │                              │
(0,100) ─────────────────── (100,100)
```

- 좌표 기준: **화면 감지(screen_detector) 후** 크롭된 PLC 화면
- 단위: % (전체 화면 대비 비율)
- 영역은 기준설정 Step2에서 **드래그로 지정**하고, 수치로도 직접 입력 가능

---

## 전처리방식 옵션

| 값 | 설명 | 적합한 경우 |
|---|------|-----------|
| `none` | 원본 그대로 | 선명한 화면, 높은 대비 |
| `grayscale` | 그레이스케일 변환 | 컬러 배경 제거 필요 시 |
| `grayscale+threshold` | 그레이 + 적응 이진화 | 대부분의 PLC 수치 영역 (기본 권장) |
| `invert` | 반전 (어두운 배경 → 밝은 배경) | 검은 배경에 흰/녹색 숫자 |
| `invert+threshold` | 반전 + 이진화 | 어두운 배경 PLC 화면 |

---

## inspection_templates 테이블 매핑

```sql
CREATE TABLE inspection_templates (
    id            TEXT PRIMARY KEY,
    equipment_id  TEXT NOT NULL REFERENCES equipments(id),
    name          TEXT NOT NULL,           -- 템플릿명
    judge_type    TEXT NOT NULL DEFAULT 'numeric',  -- numeric/signal/color
    roi_x         REAL NOT NULL,           -- ROI_X (%)
    roi_y         REAL NOT NULL,           -- ROI_Y (%)
    roi_w         REAL NOT NULL,           -- ROI_Width (%)
    roi_h         REAL NOT NULL,           -- ROI_Height (%)
    digits        INTEGER DEFAULT 3,       -- 자릿수
    has_decimal   BOOLEAN DEFAULT FALSE,   -- 소수점 여부
    preprocess    TEXT DEFAULT 'grayscale+threshold',
    ok_min        REAL,                    -- 수치형: OK 최소값
    ok_max        REAL,                    -- 수치형: OK 최대값
    ok_keywords   TEXT,                    -- 신호형: "OK,RUN,ON"
    ng_keywords   TEXT,                    -- 신호형: "NG,STOP,ERROR"
    color_map     TEXT,                    -- 색상형: JSON {"green":"ok","red":"ng"}
    sort_order    INTEGER DEFAULT 0,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```
