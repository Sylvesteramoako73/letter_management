"""Digital signatures on approved letters.

Each approved PDF is certified with the company's signing certificate and allows no further
changes, so any edit afterwards shows as tampering in a PDF reader and in the app's check.

The certificate is self-issued ("SIGL Letter Desk") and created on first use, with its private
key stored encrypted by SECRET_KEY. PDF readers show a self-issued signature as valid but of
unknown identity; to get a trusted mark, buy a document-signing certificate and set
SIGNING_KEY_PEM and SIGNING_CERT_PEM (and SIGNING_KEY_PASSWORD if the key is encrypted).
"""

import datetime
import hashlib
import os
from io import BytesIO

from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.keys import load_private_key_from_pemder_data
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

KEY_SETTING = "signing_key_pem"
CERT_SETTING = "signing_cert_pem"
FIELD_NAME = "SIGL-Approval"
REASON_PREFIX = "Approved by the Managing Director of Swami India Ghana Limited. Ref "


def _passphrase() -> bytes:
    # Same fallback as the app's session key, so local runs work without configuration.
    return (os.environ.get("SECRET_KEY") or "dev-only-change-this").encode()


def _new_certificate():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "GH"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Swami India Ghana Limited"),
        x509.NameAttribute(NameOID.COMMON_NAME, "SIGL Letter Desk"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(_passphrase())
    )
    return key_pem.decode(), certificate.public_bytes(serialization.Encoding.PEM).decode()


def _setting(connection, key):
    row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _credentials(connection):
    """(private key PEM, its passphrase, certificate PEM), creating the company certificate on first use."""
    if os.environ.get("SIGNING_KEY_PEM") and os.environ.get("SIGNING_CERT_PEM"):
        password = os.environ.get("SIGNING_KEY_PASSWORD")
        return os.environ["SIGNING_KEY_PEM"].encode(), password.encode() if password else None, os.environ["SIGNING_CERT_PEM"].encode()
    if _setting(connection, KEY_SETTING) is None:
        key_pem, cert_pem = _new_certificate()
        # Two instances may race on first use; whichever insert lands first wins and both read it back.
        for key, value in ((KEY_SETTING, key_pem), (CERT_SETTING, cert_pem)):
            connection.execute("INSERT INTO app_settings(key, value) VALUES (?, ?) ON CONFLICT DO NOTHING", (key, value))
        connection.commit()
    return _setting(connection, KEY_SETTING).encode(), _passphrase(), _setting(connection, CERT_SETTING).encode()


def _certificate(cert_pem: bytes):
    return asn1_x509.Certificate.load(x509.load_pem_x509_certificate(cert_pem).public_bytes(serialization.Encoding.DER))


def sign_pdf(connection, pdf: bytes, our_reference: str) -> bytes:
    """Certify the PDF so that no change is permitted afterwards."""
    key_pem, passphrase, cert_pem = _credentials(connection)
    signer = signers.SimpleSigner(
        signing_cert=_certificate(cert_pem),
        signing_key=load_private_key_from_pemder_data(key_pem, passphrase=passphrase),
        cert_registry=None,
    )
    metadata = signers.PdfSignatureMetadata(
        field_name=FIELD_NAME,
        reason=f"{REASON_PREFIX}{our_reference}",
        location="Accra, Ghana",
        certify=True,
        docmdp_permissions=fields.MDPPerm.NO_CHANGES,
    )
    output = BytesIO()
    signers.sign_pdf(IncrementalPdfFileWriter(BytesIO(pdf)), metadata, signer=signer, output=output)
    return output.getvalue()


def verify_pdf(connection, pdf: bytes) -> dict:
    """Whether a PDF carries our signature, and whether it is unchanged since signing."""
    result = {"signed": False, "ours": False, "intact": False, "reference": None, "signed_at": None, "sha256": hashlib.sha256(pdf).hexdigest()}
    try:
        signatures = PdfFileReader(BytesIO(pdf), strict=False).embedded_signatures
    except Exception:
        return result
    signature = next((s for s in signatures if s.field_name == FIELD_NAME), None)
    if signature is None:
        return result
    result["signed"] = True
    _, _, cert_pem = _credentials(connection)
    ours = _certificate(cert_pem)
    result["ours"] = signature.signer_cert.dump() == ours.dump()
    status = validate_pdf_signature(signature, ValidationContext(trust_roots=[ours]))
    result["intact"] = bool(status.intact and status.valid and status.coverage.name == "ENTIRE_FILE")
    reason = str(signature.sig_object.get("/Reason", ""))
    if reason.startswith(REASON_PREFIX):
        result["reference"] = reason[len(REASON_PREFIX):]
    if status.signer_reported_dt:
        result["signed_at"] = status.signer_reported_dt.isoformat()
    return result
