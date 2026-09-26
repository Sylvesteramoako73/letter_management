"""Supabase Storage for scanned documents.

Vercel rejects request and response bodies over 4.5 MB, so large scans cannot
pass through the app. When storage is configured the browser uploads straight
to Supabase with a short-lived signed URL, and downloads are redirected to a
signed URL. Without configuration (tests, offline development) files stay in
the database as before.
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import quote

BUCKET = "letters"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_bucket_ready = False


def _base_url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def _key() -> str:
    return (
        os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()


def enabled() -> bool:
    return bool(_base_url() and _key())


def _headers(extra=None) -> dict:
    key = _key()
    headers = {"apikey": key}
    # Legacy service-role keys are JWTs; the newer sb_secret_ keys go in apikey only.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    headers.update(extra or {})
    return headers


def _request(method: str, path: str, body=None, headers=None) -> bytes:
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    extra = {"Content-Type": "application/json"} if isinstance(body, (dict, list)) else {}
    extra.update(headers or {})
    request = urllib.request.Request(
        f"{_base_url()}/storage/v1{path}", data=data, method=method, headers=_headers(extra)
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Supabase Storage {method} {path} failed ({error.code}): {detail}") from None


def _object_path(path: str) -> str:
    return quote(path, safe="/")


def ensure_bucket() -> None:
    global _bucket_ready
    if _bucket_ready:
        return
    try:
        _request("GET", f"/bucket/{BUCKET}")
    except RuntimeError:
        _request(
            "POST",
            "/bucket",
            {"id": BUCKET, "name": BUCKET, "public": False, "file_size_limit": MAX_UPLOAD_BYTES},
        )
    _bucket_ready = True


def create_upload_url(path: str) -> str:
    """Signed URL the browser can PUT the file to (valid for two hours)."""
    ensure_bucket()
    result = json.loads(_request("POST", f"/object/upload/sign/{BUCKET}/{_object_path(path)}", {}))
    return f"{_base_url()}/storage/v1{result['url']}"


def download(path: str) -> bytes:
    return _request("GET", f"/object/{BUCKET}/{_object_path(path)}")


def signed_download_url(path: str, filename: str | None = None, expires_in: int = 300) -> str:
    result = json.loads(
        _request("POST", f"/object/sign/{BUCKET}/{_object_path(path)}", {"expiresIn": expires_in})
    )
    url = f"{_base_url()}/storage/v1{result['signedURL']}"
    if filename:
        url += f"&download={quote(filename)}"
    return url
