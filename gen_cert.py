"""자체 서명 SSL 인증서 생성 (로컬 네트워크 HTTPS용)"""
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime, ipaddress, os

def generate_cert(cert_dir="certs"):
    os.makedirs(cert_dir, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "PLC OCR Agent"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "WizFactory"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                x509.IPAddress(ipaddress.IPv4Network("192.168.0.0/16").network_address),
            ] + [
                x509.IPAddress(ipaddress.IPv4Address(f"192.168.{a}.{b}"))
                for a in range(256) for b in [1, 52, 59, 100]  # 흔한 IP
            ][:20]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_path = os.path.join(cert_dir, "key.pem")
    cert_path = os.path.join(cert_dir, "cert.pem")

    with open(key_path, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                   serialization.PrivateFormat.TraditionalOpenSSL,
                                   serialization.NoEncryption()))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Generated: {cert_path}, {key_path}")
    return cert_path, key_path

if __name__ == "__main__":
    generate_cert()
