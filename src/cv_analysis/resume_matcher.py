"""Explainable skill matching between a CV and a job's required skills."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.cv_analysis.skills_extractor import canonicalize_skill_list, extract_skills


@dataclass(frozen=True)
class SkillMatchResult:
    matched_skills: list[str]
    missing_skills: list[str]
    required_skills: list[str]
    score: float | None
    status: str
    explanation: str
    matched_count: int = 0
    required_count: int = 0


def match_skills(extracted: list[str], required: list[str]) -> SkillMatchResult:
    """Compute the MVP skill score from configured job requirements.

    ``score = matched / required * 100``. When a job has no configured required
    skills the result is ``NULL`` / ``NOT_SCORABLE`` (never an automatic 100).
    ``importance`` is shown to HR but does not change this transparent formula.
    """
    extracted_set = set(extract_skills(" | ".join(extracted))) | set(extracted)
    requirements = canonicalize_skill_list(required)

    if not requirements:
        return SkillMatchResult(
            matched_skills=[],
            missing_skills=[],
            required_skills=[],
            score=None,
            status="NOT_SCORABLE",
            explanation="Vị trí chưa cấu hình kỹ năng yêu cầu nên không thể chấm điểm.",
            required_count=0,
        )

    matched = [skill for skill in requirements if skill in extracted_set]
    missing = [skill for skill in requirements if skill not in extracted_set]
    score = round(len(matched) / len(requirements) * 100, 2)
    status = "SUCCESS"

    if not matched:
        explanation = "Không tìm thấy kỹ năng yêu cầu nào trong CV."
    elif missing:
        explanation = (
            f"Tìm thấy {len(matched)}/{len(requirements)} kỹ năng yêu cầu. "
            f"Còn thiếu: {', '.join(missing)}."
        )
    else:
        explanation = f"Tìm thấy đủ {len(requirements)}/{len(requirements)} kỹ năng yêu cầu."

    return SkillMatchResult(
        matched_skills=matched,
        missing_skills=missing,
        required_skills=requirements,
        score=score,
        status=status,
        explanation=explanation,
        matched_count=len(matched),
        required_count=len(requirements),
    )


def analyze_text_against_job(text: str, required: list[str]) -> tuple[list[str], SkillMatchResult]:
    extracted = extract_skills(text)
    return extracted, match_skills(extracted, required)


def score_label(score: float | None, status: str) -> str:
    if status == "NOT_SCORABLE" or score is None:
        return "Không chấm được"
    if score >= 80:
        return "Rất phù hợp"
    if score >= 60:
        return "Phù hợp"
    if score >= 40:
        return "Cần xem xét"
    return "Ít phù hợp"
