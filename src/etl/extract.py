"""Extract stage: CSV, Excel and JSON API readers."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import requests

from src import config
from src.constants import CANONICAL_ETL_COLUMNS, ETL_COLUMN_ALIASES


class ExtractionError(ValueError):
    pass


def text_key(value: object) -> str:
    """Normalize a header for alias matching (lowercase, no accents, no extra spaces)."""
    import unicodedata

    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = text.lower().replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def _sniff_delimiter(sample: str) -> str:
    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    candidates = {",": first_line.count(","), ";": first_line.count(";"), "\t": first_line.count("\t"), "|": first_line.count("|")}
    delimiter = max(candidates, key=candidates.get)
    return delimiter if candidates[delimiter] > 0 else ","


def read_csv_bytes(data: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            text = data.decode(encoding)
            delimiter = _sniff_delimiter(text)
            return pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    raise ExtractionError(f"Không đọc được CSV: {last_error}")


def read_excel_bytes(data: bytes) -> pd.DataFrame:
    try:
        return pd.read_excel(io.BytesIO(data), dtype=str, keep_default_na=False)
    except Exception as exc:  # pandas surfaces several engine errors
        raise ExtractionError(f"Không đọc được Excel .xlsx: {exc}") from exc


def read_tabular_bytes(data: bytes, filename: str) -> pd.DataFrame:
    suffix = Path(filename or "").suffix.lower()
    if not data:
        raise ExtractionError("Tệp rỗng.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ExtractionError(f"Tệp vượt quá giới hạn {config.MAX_UPLOAD_MB} MB.")
    if suffix == ".csv":
        frame = read_csv_bytes(data)
    elif suffix == ".xlsx":
        frame = read_excel_bytes(data)
    elif suffix == ".xls":
        raise ExtractionError("Định dạng .xls cũ chưa hỗ trợ; vui lòng lưu sang .xlsx.")
    else:
        raise ExtractionError("Chỉ hỗ trợ tệp CSV hoặc Excel .xlsx.")
    if frame.empty:
        raise ExtractionError("Tệp không có dòng dữ liệu.")
    if len(frame) > config.MAX_ETL_ROWS:
        raise ExtractionError(f"Tệp có {len(frame):,} dòng, vượt giới hạn {config.MAX_ETL_ROWS:,}.")
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def read_api_payload(payload: object) -> pd.DataFrame:
    """Convert a JSON array/object into a DataFrame for the API extension."""
    if isinstance(payload, dict):
        # Accept common envelopes: {"data": [...]}, {"results": [...]}, {"items": [...]}
        for key in ("data", "results", "items", "records", "candidates"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise ExtractionError("JSON phải là một mảng bản ghi hoặc object chứa mảng dữ liệu.")
    if not payload:
        raise ExtractionError("JSON không có bản ghi nào.")
    if not all(isinstance(item, dict) for item in payload):
        raise ExtractionError("Mỗi phần tử JSON phải là một object.")
    return pd.DataFrame(payload).astype(str)


def fetch_api_json(url: str, timeout: int = 15) -> pd.DataFrame:
    if not url.startswith(("http://", "https://")):
        raise ExtractionError("URL API phải bắt đầu bằng http:// hoặc https://.")
    try:
        response = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
        response.raise_for_status()
        if len(response.content) > config.MAX_UPLOAD_BYTES:
            raise ExtractionError("Phản hồi API vượt quá giới hạn kích thước.")
        payload = response.json()
    except requests.RequestException as exc:
        raise ExtractionError(f"Không gọi được API: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ExtractionError("Phản hồi API không phải JSON hợp lệ.") from exc
    return read_api_payload(payload)


def detect_column_mapping(columns: list[str]) -> dict[str, str | None]:
    """Return canonical target column -> detected source column."""
    normalized_sources = {column: text_key(column) for column in columns}
    mapping: dict[str, str | None] = {}
    for target in CANONICAL_ETL_COLUMNS:
        aliases = {text_key(alias) for alias in ETL_COLUMN_ALIASES[target]}
        match = next((source for source, key in normalized_sources.items() if key in aliases), None)
        mapping[target] = match
    return mapping


def preview_frame(frame: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    return frame.head(limit).copy()
