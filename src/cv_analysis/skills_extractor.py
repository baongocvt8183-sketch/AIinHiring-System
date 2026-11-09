"""Deterministic, local skill extraction using a curated dictionary + regex.

No CV text is sent to an external AI service. The dictionary is intentionally
small and explainable so results can be audited during the MVP demo.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# canonical name -> aliases found in Vietnamese/English CVs
SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "Python": ("python", "py"),
    "Java": ("java",),
    "JavaScript": ("javascript", "js", "es6"),
    "TypeScript": ("typescript", "ts"),
    "C++": ("c++", "cpp"),
    "C#": ("c#", "csharp", "c sharp"),
    ".NET": (".net", "dotnet", "asp.net", "asp net"),
    "SQL": ("sql", "truy van sql", "truy vấn sql"),
    "PostgreSQL": ("postgresql", "postgres", "postgre"),
    "MySQL": ("mysql",),
    "SQL Server": ("sql server", "mssql"),
    "MongoDB": ("mongodb", "mongo db"),
    "Redis": ("redis",),
    "Pandas": ("pandas",),
    "NumPy": ("numpy",),
    "Scikit-learn": ("scikit-learn", "scikit learn", "sklearn"),
    "TensorFlow": ("tensorflow", "tensor flow"),
    "PyTorch": ("pytorch", "py torch"),
    "Keras": ("keras",),
    "OpenCV": ("opencv", "open cv"),
    "NLP": ("nlp", "natural language processing", "xu ly ngon ngu tu nhien", "xử lý ngôn ngữ tự nhiên"),
    "Machine Learning": ("machine learning", "hoc may", "học máy", "ml"),
    "Deep Learning": ("deep learning", "hoc sau", "học sâu"),
    "Computer Vision": ("computer vision", "thi giac may tinh", "thị giác máy tính"),
    "Data Analysis": ("data analysis", "phan tich du lieu", "phân tích dữ liệu"),
    "Data Visualization": ("data visualization", "truc quan hoa du lieu", "trực quan hóa dữ liệu"),
    "Power BI": ("power bi", "powerbi"),
    "Tableau": ("tableau",),
    "Excel": ("excel", "microsoft excel"),
    "Statistics": ("statistics", "thong ke", "thống kê"),
    "A/B Testing": ("a/b testing", "ab testing", "a b testing"),
    "ETL": ("etl", "extract transform load"),
    "Airflow": ("airflow", "apache airflow"),
    "Spark": ("spark", "apache spark", "pyspark"),
    "Hadoop": ("hadoop",),
    "Kafka": ("kafka",),
    "Docker": ("docker",),
    "Kubernetes": ("kubernetes", "k8s"),
    "Git": ("git", "github", "gitlab"),
    "Linux": ("linux", "ubuntu", "unix"),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure", "microsoft azure"),
    "GCP": ("gcp", "google cloud"),
    "REST API": ("rest api", "restful", "rest"),
    "GraphQL": ("graphql",),
    "Django": ("django",),
    "Flask": ("flask",),
    "FastAPI": ("fastapi", "fast api"),
    "Streamlit": ("streamlit",),
    "React": ("react", "reactjs", "react.js"),
    "Vue": ("vue", "vuejs", "vue.js"),
    "Angular": ("angular",),
    "Node.js": ("node.js", "nodejs", "node js"),
    "HTML": ("html", "html5"),
    "CSS": ("css", "css3"),
    "Tailwind": ("tailwind", "tailwindcss"),
    "Figma": ("figma",),
    "Agile": ("agile",),
    "Scrum": ("scrum",),
    "Jira": ("jira",),
    "Communication": ("communication", "giao tiep", "giao tiếp"),
    "Teamwork": ("teamwork", "lam viec nhom", "làm việc nhóm"),
    "Problem Solving": ("problem solving", "giai quyet van de", "giải quyết vấn đề"),
    "English": ("english", "tieng anh", "tiếng anh", "ielts", "toeic"),
    "Japanese": ("japanese", "tieng nhat", "tiếng nhật", "jlpt"),
}

# Prevent the generic alias "ml" from matching inside normal words.
SKILL_ALIASES["Machine Learning"] = tuple(
    alias for alias in SKILL_ALIASES["Machine Learning"] if alias != "ml"
)


def normalize_text(text: str) -> str:
    """Lowercase and remove Vietnamese diacritics for matching."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return " ".join(text.lower().split())


def _compile_pattern(alias: str) -> re.Pattern:
    escaped = re.escape(normalize_text(alias))
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)


_COMPILED: list[tuple[str, tuple[re.Pattern, ...]]] = [
    (canonical, tuple(_compile_pattern(alias) for alias in aliases))
    for canonical, aliases in SKILL_ALIASES.items()
]

_SKILL_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in SKILL_ALIASES.items():
    _SKILL_LOOKUP[normalize_text(_canonical)] = _canonical
    for _alias in _aliases:
        _SKILL_LOOKUP[normalize_text(_alias)] = _canonical


def extract_skills(text: str) -> list[str]:
    """Return canonical skills found in the text, in dictionary order."""
    normalized = normalize_text(text)
    if not normalized:
        return []
    found: list[str] = []
    for canonical, patterns in _COMPILED:
        if any(pattern.search(normalized) for pattern in patterns):
            found.append(canonical)
    return found


def canonicalize_skill(value: str) -> str | None:
    key = normalize_text(value)
    if not key:
        return None
    if key in _SKILL_LOOKUP:
        return _SKILL_LOOKUP[key]
    # Try a contained dictionary skill; keep the configured name otherwise.
    found = extract_skills(value)
    if found:
        return found[0]
    return " ".join(str(value).split())[:100]


def canonicalize_skill_list(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        canonical = canonicalize_skill(value)
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def _section_lines(text: str, headings: tuple[str, ...], limit: int = 4) -> list[str]:
    lines = [line.strip(" •\t-") for line in text.splitlines() if line.strip()]
    heading_keys = tuple(normalize_text(h) for h in headings)
    collected: list[str] = []
    in_section = False
    for line in lines:
        normalized = normalize_text(line)
        if any(normalized.startswith(key) for key in heading_keys):
            in_section = True
            remainder = normalized
            for key in heading_keys:
                if remainder.startswith(key):
                    remainder = remainder[len(key):].strip(" :")
                    break
            if remainder:
                collected.append(remainder)
            continue
        if in_section:
            # A new likely heading ends the current section.
            if len(line) < 40 and (line.endswith(":") or line.isupper()):
                break
            collected.append(line)
            if len(collected) >= limit:
                break
    return collected[:limit]


def summarize_sections(text: str) -> tuple[str, str]:
    """Very small local heuristic summariser for experience/projects sections."""
    experience = _section_lines(text, ("experience", "kinh nghiem", "kinh nghiệm", "work experience"))
    projects = _section_lines(text, ("project", "du an", "dự án", "projects"))
    exp_summary = " • ".join(experience)[:1200] if experience else ""
    project_summary = " • ".join(projects)[:1200] if projects else ""
    if not exp_summary:
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split())[:6000])
        picks = [s for s in sentences if re.search(r"\d+\s*(nam|năm|year)", normalize_text(s))]
        exp_summary = " ".join(picks[:3])[:1200]
    return exp_summary, project_summary
