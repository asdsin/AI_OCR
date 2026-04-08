"""
테스트 데이터 삽입 스크립트
실행: cd backend && python seed_data.py
이미 데이터가 있으면 중복 삽입하지 않음
"""
import json
from app.db import SessionLocal, init_db
from app.models import Equipment, InspectionTemplate, JudgmentRule

init_db()
db = SessionLocal()

# ═══ 설비 3개 ═══
equipments_data = [
    {"equipment_code": "EQ-001", "equipment_name": "건조기 1호기", "line_name": "A라인", "location_name": "1공정", "qr_value": "EQ001"},
    {"equipment_code": "EQ-002", "equipment_name": "프레스 2호기", "line_name": "B라인", "location_name": "2공정", "qr_value": "EQ002"},
    {"equipment_code": "EQ-003", "equipment_name": "컨베이어 3호기", "line_name": "C라인", "location_name": "3공정", "qr_value": "EQ003"},
]

created_equipments = {}
for ed in equipments_data:
    existing = db.query(Equipment).filter(Equipment.equipment_code == ed["equipment_code"]).first()
    if existing:
        print(f"  [스킵] 설비 {ed['equipment_code']} 이미 존재")
        created_equipments[ed["equipment_code"]] = existing
    else:
        eq = Equipment(**ed)
        db.add(eq)
        db.flush()
        created_equipments[ed["equipment_code"]] = eq
        print(f"  [생성] 설비 {ed['equipment_code']} → ID {eq.id}")

# ═══ 템플릿 (설비별 ROI) ═══
templates_data = [
    # 건조기: 온도 표시부 (수치형)
    {"equip": "EQ-001", "template_name": "온도 표시부", "judgment_type": "numeric",
     "roi_x": 12, "roi_y": 25, "roi_width": 20, "roi_height": 8, "preprocess_type": "grayscale+threshold"},
    # 건조기: 가동등 (신호형)
    {"equip": "EQ-001", "template_name": "가동등", "judgment_type": "signal",
     "roi_x": 50, "roi_y": 70, "roi_width": 10, "roi_height": 10, "preprocess_type": "grayscale"},
    # 프레스: 압력 게이지 (수치형)
    {"equip": "EQ-002", "template_name": "압력 게이지", "judgment_type": "numeric",
     "roi_x": 30, "roi_y": 40, "roi_width": 15, "roi_height": 10, "preprocess_type": "grayscale+threshold"},
    # 컨베이어: 상태등 (색상형)
    {"equip": "EQ-003", "template_name": "상태등", "judgment_type": "color",
     "roi_x": 60, "roi_y": 20, "roi_width": 8, "roi_height": 8, "preprocess_type": "none"},
]

created_templates = {}
for td in templates_data:
    eq = created_equipments[td["equip"]]
    key = f"{td['equip']}_{td['template_name']}"
    existing = db.query(InspectionTemplate).filter(
        InspectionTemplate.equipment_id == eq.id,
        InspectionTemplate.template_name == td["template_name"]
    ).first()
    if existing:
        print(f"  [스킵] 템플릿 {key} 이미 존재")
        created_templates[key] = existing
    else:
        tmpl = InspectionTemplate(
            equipment_id=eq.id,
            template_name=td["template_name"],
            judgment_type=td["judgment_type"],
            roi_x=td["roi_x"], roi_y=td["roi_y"],
            roi_width=td["roi_width"], roi_height=td["roi_height"],
            preprocess_type=td.get("preprocess_type"),
        )
        db.add(tmpl)
        db.flush()
        created_templates[key] = tmpl
        print(f"  [생성] 템플릿 {key} → ID {tmpl.id}")

# ═══ 규칙 (템플릿별 판정 기준) ═══
rules_data = [
    # 온도: 20~80℃
    {"equip": "EQ-001", "tmpl": "온도 표시부", "judgment_type": "numeric",
     "min_value": 20.0, "max_value": 80.0, "unit": "℃"},
    # 가동등: ON=밝기150이상, OFF=50이하
    {"equip": "EQ-001", "tmpl": "가동등", "judgment_type": "signal",
     "signal_on_threshold": 150, "signal_off_threshold": 50, "target_text": "ON,RUN"},
    # 압력: 1.0~5.0 bar
    {"equip": "EQ-002", "tmpl": "압력 게이지", "judgment_type": "numeric",
     "min_value": 1.0, "max_value": 5.0, "unit": "bar"},
    # 상태등: 색상 매핑
    {"equip": "EQ-003", "tmpl": "상태등", "judgment_type": "color",
     "color_mapping_json": json.dumps({"green": "가동", "red": "정지", "blue": "대기"}, ensure_ascii=False)},
]

for rd in rules_data:
    eq = created_equipments[rd["equip"]]
    tmpl = created_templates[f"{rd['equip']}_{rd['tmpl']}"]
    existing = db.query(JudgmentRule).filter(
        JudgmentRule.template_id == tmpl.id
    ).first()
    if existing:
        print(f"  [스킵] 규칙 {rd['equip']}_{rd['tmpl']} 이미 존재")
    else:
        rule = JudgmentRule(
            equipment_id=eq.id,
            template_id=tmpl.id,
            judgment_type=rd["judgment_type"],
            min_value=rd.get("min_value"),
            max_value=rd.get("max_value"),
            target_text=rd.get("target_text"),
            signal_on_threshold=rd.get("signal_on_threshold"),
            signal_off_threshold=rd.get("signal_off_threshold"),
            color_mapping_json=rd.get("color_mapping_json"),
            unit=rd.get("unit"),
        )
        db.add(rule)
        print(f"  [생성] 규칙 {rd['equip']}_{rd['tmpl']}")

db.commit()
db.close()
print("\n[완료] 시드 데이터 삽입 완료")
