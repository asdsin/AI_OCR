"""데모 데이터 투입"""
import httpx
B='http://localhost:8001/api/master'
Q='http://localhost:8001/api/qr'

c=httpx.post(f'{B}/companies',json={'code':'LGE','name':'LG전자','industry':'전자'}).json()
d=httpx.post(f'{B}/divisions',json={'company_id':c['id'],'code':'changwon','name':'창원사업장','location':'경남 창원시'}).json()
l=httpx.post(f'{B}/lines',json={'division_id':d['id'],'code':'DRY-A','name':'건조 A라인','line_type':'건조'}).json()
p=httpx.post(f'{B}/processes',json={'line_id':l['id'],'code':'NIR-DRY','name':'NIR 건조','process_type':'건조','sequence':1}).json()
e=httpx.post(f'{B}/equipments',json={'process_id':p['id'],'code':'NIR-001','name':'NIR 건조로 #1','equipment_type':'건조','plc_type':'LS XGT'}).json()
print(f"Equipment: {e['id']}")

for qr,scr,desc in [
    ('NIR001-SCR','SCR 전류 화면','상단/하단 8개 히터 그룹 전류값'),
    ('NIR001-TEMP','히터 온도 화면','파트별 히터 온도 설정/현재값'),
    ('NIR001-SET','히터 설정 화면','히터 설정값 + 바 그래프'),
]:
    r=httpx.post(f'{Q}/points',json={'equipment_id':e['id'],'qr_code':qr,'screen_name':scr,'description':desc})
    print(f"QR {qr}: {r.status_code}")

print("Done")
