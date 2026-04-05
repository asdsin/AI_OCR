# PLC OCR Agent

PLC 화면 촬영 → 자동 OCR → OK/NG 판정 시스템

## 빠른 시작

```bash
pip install -r requirements.txt
python run.py
```

브라우저에서 `http://localhost:8001` 접속

## 기능

- **기준정보 관리**: 업체 > 사업부 > 라인 > 공정 > 설비 > QR포인트 계층구조
- **QR 기반 식별**: 설비별 여러 QR 포인트 등록, 실시간 QR 스캔
- **시각 기준설정**: 기준 사진 촬영 → OCR 분석 → 항목 터치 선택 → 조건 입력
- **자동 판정**: 프로필 기반 OK/NG 판정 (범위, 이상/이하, 동일, 텍스트)
- **오판정 학습**: 값 오류/판정 오류/노이즈 수정 → 학습 데이터 축적

## 기술 스택

- FastAPI + SQLite + EasyOCR
- 단일 HTML (모바일 PWA 대응)
- jsQR (실시간 QR 스캔)
