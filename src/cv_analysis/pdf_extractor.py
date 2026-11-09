"""Secure PDF upload, private storage and text extraction with PyMuPDF."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:  # PyMuPDF >= 1.24 exposes the modern module name
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz

from src import config


ALLOWED_MIME_TYPES = {"application/pdf", "application/octet-stream"}


class UploadValidationError(ValueError):
    pass


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    path: Path
    sha256: str
    size_bytes: int
    mime_type: str
    original_filename: str


@dataclass(frozen=True)
class PDFExtraction:
    text: str
    page_count: int
    char_count: int
    needs_ocr: bool
    error: str | None = None

    @property
    def has_text(self) -> bool:
        return self.char_count >= config.MIN_PDF_TEXT_CHARS and not self.error


def validate_pdf_upload(filename: str, data: bytes, mime_type: str | None = None) -> str:
    """Validate extension, size, magic bytes and MIME type. Returns normalized MIME."""
    safe_name = Path(filename or "").name
    if not safe_name.lower().endswith(".pdf"):
        raise UploadValidationError("Chỉ chấp nhận tệp CV định dạng PDF.")
    if not data:
        raise UploadValidationError("Tệp PDF rỗng.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise UploadValidationError(f"Tệp vượt quá giới hạn {config.MAX_UPLOAD_MB} MB.")
    if not data.startswith(b"%PDF-"):
        raise UploadValidationError("Nội dung tệp không phải PDF hợp lệ.")
    resolved_mime = (mime_type or "application/pdf").lower()
    if resolved_mime not in ALLOWED_MIME_TYPES:
        raise UploadValidationError(f"Loại nội dung không được phép: {resolved_mime}")
    return "application/pdf"


def safe_original_filename(filename: str) -> str:
    """Remove e-mail-like and path content from the stored display name."""
    name = Path(filename or "cv.pdf").name
    name = re.sub(r"[^\w\s.\-()]", "_", name, flags=re.UNICODE)
    return name[:255] or "cv.pdf"


def store_pdf(data: bytes, original_filename: str, mime_type: str = "application/pdf") -> StoredFile:
    """Store the file under a random key in the private upload directory."""
    config.ensure_directories()
    now = datetime.now(timezone.utc)
    storage_key = f"{now:%Y/%m}/{uuid.uuid4().hex}.pdf"
    path = resolve_storage_path(storage_key, create_parent=True)
    path.write_bytes(data)
    return StoredFile(
        storage_key=storage_key,
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        mime_type=mime_type,
        original_filename=safe_original_filename(original_filename),
    )


def resolve_storage_path(storage_key: str, *, create_parent: bool = False) -> Path:
    """Resolve a storage key while preventing path traversal."""
    root = config.UPLOAD_DIR.resolve()
    candidate = (root / storage_key).resolve()
    if root not in candidate.parents and candidate != root:
        raise UploadValidationError("Đường dẫn tệp không hợp lệ.")
    if create_parent:
        candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def extract_pdf_text(path: str | Path) -> PDFExtraction:
    try:
        with fitz.open(str(path)) as document:
            if document.needs_pass:
                return PDFExtraction("", 0, 0, False, "PDF được bảo vệ bằng mật khẩu.")
            pages = [page.get_text("text") for page in document]
            page_count = document.page_count
    except Exception as exc:  # corrupt PDFs raise many PyMuPDF errors
        return PDFExtraction("", 0, 0, False, f"Không đọc được PDF: {exc}")

    text = "\n".join(pages).replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    char_count = len(text)
    return PDFExtraction(
        text=text,
        page_count=page_count,
        char_count=char_count,
        needs_ocr=char_count < config.MIN_PDF_TEXT_CHARS,
        error=None,
    )


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
