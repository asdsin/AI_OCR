"""
서버 실행 스크립트
- HTTP  :8001 (기본)
- HTTPS :8443 (스마트폰 카메라 권한용, 자체 서명 인증서)
"""
import uvicorn, os, sys, threading

def run_http():
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, log_level="info")

def run_https():
    cert = os.path.join(os.path.dirname(__file__), "certs", "cert.pem")
    key = os.path.join(os.path.dirname(__file__), "certs", "key.pem")
    if not os.path.exists(cert):
        print("[HTTPS] 인증서 없음 — python gen_cert.py 실행 필요")
        return
    print(f"[HTTPS] https://0.0.0.0:8443 시작")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8443,
                ssl_certfile=cert, ssl_keyfile=key, log_level="info")

if __name__ == "__main__":
    if "--https-only" in sys.argv:
        run_https()
    elif "--http-only" in sys.argv:
        run_http()
    else:
        t = threading.Thread(target=run_https, daemon=True)
        t.start()
        run_http()
