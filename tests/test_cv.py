from __future__ import annotations

import pytest

from src.cv_analysis.pdf_extractor import (
    UploadValidationError,
    extract_pdf_text,
    resolve_storage_path,
    store_pdf,
    validate_pdf_upload,
)
from src.cv_analysis.resume_matcher import match_skills, score_label
from src.cv_analysis.skills_extractor import canonicalize_skill_list, extract_skills, summarize_sections
from src.database.sample_data import write_sample_files


def test_skill_extraction_handles_symbols_and_vietnamese():
    text = (
        "Kinh nghiệm Python, SQL, C++, C#, JavaScript, Java, scikit-learn, PyTorch. "
        "Học máy và trí tuệ nhân tạo. Tiếng Anh tốt, làm việc nhóm."
    )
    skills = extract_skills(text)
    for expected in ["Python", "SQL", "C++", "C#", "JavaScript", "Java", "Scikit-learn", "PyTorch", "Machine Learning", "English", "Teamwork"]:
        assert expected in skills
    assert extract_skills("We are excellent at communication.") == ["Communication"]
    assert "Java" not in extract_skills("JavaScript only")


def test_skill_canonicalization():
    assert canonicalize_skill_list(["python", "PowerBI", "unknown-tool"]) == ["Python", "Power BI", "unknown-tool"]


def test_skill_match_formula_and_not_scorable():
    result = match_skills(["Python", "SQL"], ["Python", "SQL", "Docker"])
    assert result.score == pytest.approx(66.67, abs=0.01)
    assert result.matched_skills == ["Python", "SQL"]
    assert result.missing_skills == ["Docker"]
    assert "Docker" in result.explanation

    empty = match_skills(["Python"], [])
    assert empty.score is None
    assert empty.status == "NOT_SCORABLE"
    assert score_label(None, "NOT_SCORABLE") == "Không chấm được"


def test_pdf_text_extraction_and_ocr_detection():
    paths = write_sample_files()
    text_pdf = extract_pdf_text(paths["cv_nguyen_van_an.pdf"])
    assert not text_pdf.error
    assert text_pdf.has_text
    assert not text_pdf.needs_ocr
    assert "PyTorch" in text_pdf.text

    scan_pdf = extract_pdf_text(paths["cv_scan_only.pdf"])
    assert not scan_pdf.error
    assert scan_pdf.needs_ocr
    assert scan_pdf.char_count < 50


def test_pdf_upload_validation_and_private_storage():
    paths = write_sample_files()
    data = paths["cv_nguyen_van_an.pdf"].read_bytes()
    assert validate_pdf_upload("cv.pdf", data, "application/pdf") == "application/pdf"

    with pytest.raises(UploadValidationError):
        validate_pdf_upload("cv.txt", data, "text/plain")
    with pytest.raises(UploadValidationError):
        validate_pdf_upload("cv.pdf", b"not a pdf", "application/pdf")
    with pytest.raises(UploadValidationError):
        validate_pdf_upload("cv.pdf", b"", "application/pdf")

    stored = store_pdf(data, "CV Nguyễn Văn An.pdf")
    assert stored.path.exists()
    assert stored.storage_key.endswith(".pdf")
    assert resolve_storage_path(stored.storage_key) == stored.path
    with pytest.raises(UploadValidationError):
        resolve_storage_path("../../etc/passwd")
    stored.path.unlink(missing_ok=True)


def test_summarize_sections():
    text = "SKILLS\nPython\nEXPERIENCE\nAI Engineer 2021 - 2024\nPROJECTS\nChatbot\nEDUCATION\nBSc"
    experience, projects = summarize_sections(text)
    assert "AI Engineer" in experience
    assert "Chatbot" in projects
