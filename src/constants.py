"""Shared enumerations, permissions and normalization maps."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Roles and permissions
# ---------------------------------------------------------------------------
ROLE_HR = "HR_MANAGER"
ROLE_HIRING = "HIRING_MANAGER"
ROLE_ADMIN = "ADMIN"
ROLE_AUDITOR = "AUDITOR"

ROLE_LABELS = {
    ROLE_HR: "HR Manager",
    ROLE_HIRING: "Hiring Manager",
    ROLE_ADMIN: "Quản trị viên",
    ROLE_AUDITOR: "Kiểm toán viên",
}

PERM_VIEW_DASHBOARD = "view_dashboard"
PERM_VIEW_APPLICATIONS = "view_applications"
PERM_VIEW_CANDIDATES = "view_candidates"
PERM_MANAGE_CANDIDATES = "manage_candidates"
PERM_IMPORT_DATA = "import_data"
PERM_VIEW_ETL = "view_etl"
PERM_MANAGE_JOBS = "manage_jobs"
PERM_VIEW_CV = "view_cv"
PERM_ANALYZE_CV = "analyze_cv"
PERM_REVIEW_AI = "review_ai"
PERM_VIEW_AI_RESULT = "view_ai_result"
PERM_UPDATE_PIPELINE = "update_pipeline"
PERM_ADD_NOTES = "add_notes"
PERM_MANAGE_USERS = "manage_users"
PERM_VIEW_AUDIT = "view_audit"
PERM_VIEW_PII = "view_pii"
PERM_EXPORT = "export"

ALL_PERMISSIONS = frozenset(
    {
        PERM_VIEW_DASHBOARD,
        PERM_VIEW_APPLICATIONS,
        PERM_VIEW_CANDIDATES,
        PERM_MANAGE_CANDIDATES,
        PERM_IMPORT_DATA,
        PERM_VIEW_ETL,
        PERM_MANAGE_JOBS,
        PERM_VIEW_CV,
        PERM_ANALYZE_CV,
        PERM_REVIEW_AI,
        PERM_VIEW_AI_RESULT,
        PERM_UPDATE_PIPELINE,
        PERM_ADD_NOTES,
        PERM_MANAGE_USERS,
        PERM_VIEW_AUDIT,
        PERM_VIEW_PII,
        PERM_EXPORT,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_ADMIN: ALL_PERMISSIONS,
    ROLE_HR: frozenset(
        {
            PERM_VIEW_DASHBOARD,
            PERM_VIEW_APPLICATIONS,
            PERM_VIEW_CANDIDATES,
            PERM_MANAGE_CANDIDATES,
            PERM_IMPORT_DATA,
            PERM_VIEW_ETL,
            PERM_MANAGE_JOBS,
            PERM_VIEW_CV,
            PERM_ANALYZE_CV,
            PERM_REVIEW_AI,
            PERM_VIEW_AI_RESULT,
            PERM_UPDATE_PIPELINE,
            PERM_ADD_NOTES,
            PERM_VIEW_PII,
            PERM_EXPORT,
        }
    ),
    ROLE_HIRING: frozenset(
        {
            PERM_VIEW_DASHBOARD,
            PERM_VIEW_APPLICATIONS,
            PERM_VIEW_CANDIDATES,
            PERM_VIEW_CV,
            PERM_VIEW_AI_RESULT,
            PERM_ADD_NOTES,
            PERM_EXPORT,
        }
    ),
    ROLE_AUDITOR: frozenset(
        {
            # Read-only audit access only; no candidate/PII/dashboard data.
            PERM_VIEW_AUDIT,
            PERM_EXPORT,
        }
    ),
}

# ---------------------------------------------------------------------------
# Workflow enumerations
# ---------------------------------------------------------------------------
APPLICATION_STATUSES = (
    "IN_PROGRESS",
    "HIRED",
    "REJECTED",
    "WITHDRAWN",
    "OFFER_DECLINED",
    "ON_HOLD",
)
APPLICATION_STATUS_LABELS = {
    "IN_PROGRESS": "Đang xử lý",
    "HIRED": "Đã tuyển",
    "REJECTED": "Từ chối",
    "WITHDRAWN": "Ứng viên rút",
    "OFFER_DECLINED": "Từ chối offer",
    "ON_HOLD": "Tạm dừng",
}
TERMINAL_APPLICATION_STATUSES = {"HIRED", "REJECTED", "WITHDRAWN", "OFFER_DECLINED"}

STAGE_RESULTS = ("PASSED", "FAILED", "PENDING", "SKIPPED")
STAGE_RESULT_LABELS = {
    "PASSED": "Đạt",
    "FAILED": "Không đạt",
    "PENDING": "Đang chờ",
    "SKIPPED": "Bỏ qua / rút",
}

PROCESSING_STATUSES = ("PENDING", "PROCESSING", "SUCCESS", "FAILED", "NEEDS_OCR", "NOT_SCORABLE")
REVIEW_STATUSES = ("PENDING_REVIEW", "APPROVED", "REJECTED", "REVISION_REQUESTED")
REVIEW_STATUS_LABELS = {
    "PENDING_REVIEW": "Chờ HR duyệt",
    "APPROVED": "Đã duyệt",
    "REJECTED": "Từ chối kết quả",
    "REVISION_REQUESTED": "Yêu cầu chỉnh sửa",
}
REVIEW_DECISIONS = ("APPROVED", "REJECTED", "REVISION_REQUESTED")

ETL_STATUSES = ("SUCCESS", "PARTIAL_SUCCESS", "FAILED")
AUDIT_RESULTS = ("SUCCESS", "FAILURE", "DENIED")

NOTE_TYPES = ("GENERAL", "INTERVIEW", "ASSESSMENT", "REVIEW", "SYSTEM")
NOTE_TYPE_LABELS = {
    "GENERAL": "Chung",
    "INTERVIEW": "Phỏng vấn",
    "ASSESSMENT": "Đánh giá",
    "REVIEW": "Kiểm duyệt",
    "SYSTEM": "Hệ thống",
}

DEFAULT_STAGE_NAMES = (
    "CV Screening",
    "Online Test",
    "Technical Interview",
    "HR Interview",
    "Offer",
    "Hired",
)

# ---------------------------------------------------------------------------
# Normalization maps (Vietnamese + English source values)
# ---------------------------------------------------------------------------
STATUS_ALIASES = {
    "in_progress": "IN_PROGRESS",
    "in progress": "IN_PROGRESS",
    "dang xu ly": "IN_PROGRESS",
    "đang xử lý": "IN_PROGRESS",
    "dang xu ly ho so": "IN_PROGRESS",
    "screening": "IN_PROGRESS",
    "interviewing": "IN_PROGRESS",
    "active": "IN_PROGRESS",
    "hired": "HIRED",
    "tuyen": "HIRED",
    "tuyển": "HIRED",
    "da tuyen": "HIRED",
    "đã tuyển": "HIRED",
    "accepted": "HIRED",
    "rejected": "REJECTED",
    "tu choi": "REJECTED",
    "từ chối": "REJECTED",
    "loai": "REJECTED",
    "loại": "REJECTED",
    "khong phu hop": "REJECTED",
    "withdrawn": "WITHDRAWN",
    "rut": "WITHDRAWN",
    "rút": "WITHDRAWN",
    "ung vien rut": "WITHDRAWN",
    "offer_declined": "OFFER_DECLINED",
    "offer declined": "OFFER_DECLINED",
    "declined": "OFFER_DECLINED",
    "tu choi offer": "OFFER_DECLINED",
    "on_hold": "ON_HOLD",
    "on hold": "ON_HOLD",
    "hold": "ON_HOLD",
    "tam dung": "ON_HOLD",
    "tạm dừng": "ON_HOLD",
}

STAGE_RESULT_ALIASES = {
    "passed": "PASSED",
    "pass": "PASSED",
    "dat": "PASSED",
    "đạt": "PASSED",
    "failed": "FAILED",
    "fail": "FAILED",
    "khong dat": "FAILED",
    "không đạt": "FAILED",
    "pending": "PENDING",
    "dang cho": "PENDING",
    "đang chờ": "PENDING",
    "skipped": "SKIPPED",
    "withdrawn": "SKIPPED",
    "bo qua": "SKIPPED",
    "bỏ qua": "SKIPPED",
}

ETL_COLUMN_ALIASES = {
    "full_name": (
        "full_name",
        "full name",
        "name",
        "candidate_name",
        "ho ten",
        "họ tên",
        "ho va ten",
        "họ và tên",
        "ten ung vien",
        "tên ứng viên",
    ),
    "email": ("email", "e-mail", "mail", "dia chi email", "địa chỉ email"),
    "phone": ("phone", "phone_number", "mobile", "so dien thoai", "số điện thoại", "sdt"),
    "job_title": (
        "job_title",
        "job",
        "position",
        "vi tri",
        "vị trí",
        "vi tri ung tuyen",
        "vị trí ứng tuyển",
        "cong viec",
        "công việc",
    ),
    "department": ("department", "phong ban", "phòng ban", "bo phan", "bộ phận"),
    "source_name": ("source_name", "source", "nguon", "nguồn", "kenh", "kênh"),
    "applied_at": (
        "applied_at",
        "applied_date",
        "application_date",
        "ngay ung tuyen",
        "ngày ứng tuyển",
        "ngay nop",
        "ngày nộp",
        "date",
    ),
    "current_status": ("current_status", "status", "trang thai", "trạng thái"),
    "stage": ("stage", "current_stage", "vong", "vòng", "vong tuyen", "vòng tuyển"),
    "job_description": ("job_description", "mo ta cong viec", "mô tả công việc", "description"),
    "job_skills": (
        "job_skills",
        "required_skills",
        "ky nang yeu cau",
        "kỹ năng yêu cầu",
        "skills",
    ),
}

REQUIRED_ETL_COLUMNS = ("full_name", "job_title")
CANONICAL_ETL_COLUMNS = tuple(ETL_COLUMN_ALIASES.keys())
