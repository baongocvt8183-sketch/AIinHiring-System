-- AI in Hiring — PostgreSQL schema
-- Run with: psql "$DATABASE_URL" -f sql/schema.sql
-- The application also creates an equivalent schema from SQLAlchemy models
-- (SQLite fallback) via `python scripts/init_db.py`.

CREATE TABLE IF NOT EXISTS roles (
    role_id      BIGSERIAL PRIMARY KEY,
    role_name    VARCHAR(50) NOT NULL UNIQUE,
    description  TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id        BIGSERIAL PRIMARY KEY,
    username       VARCHAR(100) NOT NULL UNIQUE,
    email          VARCHAR(255) NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    full_name      VARCHAR(200) NOT NULL,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id      BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role_id      BIGINT NOT NULL REFERENCES roles(role_id) ON DELETE RESTRICT,
    assigned_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_by  BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    PRIMARY KEY (user_id, role_id),
    CONSTRAINT ck_user_role_not_self CHECK (assigned_by IS NULL OR assigned_by <> user_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id          BIGSERIAL PRIMARY KEY,
    job_title       VARCHAR(200) NOT NULL,
    department      VARCHAR(150),
    job_description TEXT,
    source_name     VARCHAR(100),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stages (
    stage_id    BIGSERIAL PRIMARY KEY,
    stage_name  VARCHAR(100) NOT NULL UNIQUE,
    stage_order INTEGER NOT NULL UNIQUE,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id BIGSERIAL PRIMARY KEY,
    full_name    VARCHAR(200) NOT NULL,
    email        VARCHAR(255),
    phone        VARCHAR(50),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_archived  BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_candidates_email UNIQUE (email)
);
-- Email is normalized (trim + lower) before storage. The functional index
-- protects against future non-normalized writes.
CREATE UNIQUE INDEX IF NOT EXISTS uq_candidates_email_lower
    ON candidates (lower(email)) WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS applications (
    application_id   BIGSERIAL PRIMARY KEY,
    candidate_id     BIGINT NOT NULL REFERENCES candidates(candidate_id) ON DELETE RESTRICT,
    job_id           BIGINT NOT NULL REFERENCES jobs(job_id) ON DELETE RESTRICT,
    applied_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_stage_id BIGINT REFERENCES stages(stage_id) ON DELETE SET NULL,
    current_status   VARCHAR(30) NOT NULL DEFAULT 'IN_PROGRESS',
    source_name      VARCHAR(100),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_application_candidate_job UNIQUE (candidate_id, job_id),
    CONSTRAINT ck_application_status CHECK (
        current_status IN ('IN_PROGRESS','HIRED','REJECTED','WITHDRAWN','OFFER_DECLINED','ON_HOLD')
    )
);

CREATE TABLE IF NOT EXISTS user_job_assignments (
    user_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    job_id      BIGINT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_by BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    PRIMARY KEY (user_id, job_id)
);

CREATE TABLE IF NOT EXISTS application_stage_history (
    history_id     BIGSERIAL PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    stage_id       BIGINT NOT NULL REFERENCES stages(stage_id) ON DELETE RESTRICT,
    entered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    exited_at      TIMESTAMPTZ,
    result         VARCHAR(30),
    notes          TEXT,
    CONSTRAINT ck_stage_history_time CHECK (exited_at IS NULL OR exited_at >= entered_at),
    CONSTRAINT ck_stage_history_result CHECK (result IS NULL OR result IN ('PASSED','FAILED','PENDING','SKIPPED'))
);
-- At most one open stage per application.
CREATE UNIQUE INDEX IF NOT EXISTS uq_open_stage_history
    ON application_stage_history(application_id) WHERE exited_at IS NULL;

CREATE TABLE IF NOT EXISTS job_required_skills (
    job_id      BIGINT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    skill_name  VARCHAR(100) NOT NULL,
    importance  NUMERIC(4,3) NOT NULL DEFAULT 1.000,
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (job_id, skill_name),
    CONSTRAINT ck_required_skill_importance CHECK (importance >= 0 AND importance <= 1)
);

CREATE TABLE IF NOT EXISTS candidate_documents (
    document_id       BIGSERIAL PRIMARY KEY,
    candidate_id      BIGINT NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    application_id    BIGINT REFERENCES applications(application_id) ON DELETE SET NULL,
    storage_key       TEXT NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    mime_type         VARCHAR(100) NOT NULL,
    file_size_bytes   BIGINT NOT NULL,
    sha256_hash       CHAR(64),
    uploaded_by       BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_cv_analysis (
    analysis_id        BIGSERIAL PRIMARY KEY,
    application_id     BIGINT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    document_id        BIGINT REFERENCES candidate_documents(document_id) ON DELETE SET NULL,
    skills_extracted   JSONB NOT NULL DEFAULT '[]'::jsonb,
    experience_summary TEXT,
    projects_summary   TEXT,
    extracted_text     TEXT,
    skill_match_score  NUMERIC(5,2),
    missing_skills     JSONB NOT NULL DEFAULT '[]'::jsonb,
    processing_status  VARCHAR(30) NOT NULL,
    review_status      VARCHAR(30) NOT NULL DEFAULT 'PENDING_REVIEW',
    processing_error   TEXT,
    method_version     VARCHAR(100),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_skill_score CHECK (skill_match_score IS NULL OR (skill_match_score >= 0 AND skill_match_score <= 100)),
    CONSTRAINT ck_ai_processing_status CHECK (
        processing_status IN ('PENDING','PROCESSING','SUCCESS','FAILED','NEEDS_OCR','NOT_SCORABLE')
    ),
    CONSTRAINT ck_ai_review_status CHECK (
        review_status IN ('PENDING_REVIEW','APPROVED','REJECTED','REVISION_REQUESTED')
    )
);

CREATE TABLE IF NOT EXISTS ai_analysis_reviews (
    review_id   BIGSERIAL PRIMARY KEY,
    analysis_id BIGINT NOT NULL REFERENCES ai_cv_analysis(analysis_id) ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    decision    VARCHAR(30) NOT NULL,
    review_note TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_review_decision CHECK (decision IN ('APPROVED','REJECTED','REVISION_REQUESTED'))
);

CREATE TABLE IF NOT EXISTS application_notes (
    note_id        BIGSERIAL PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    author_id      BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    note_type      VARCHAR(30) NOT NULL DEFAULT 'GENERAL',
    note_text      TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etl_runs (
    etl_run_id     BIGSERIAL PRIMARY KEY,
    source_name    VARCHAR(255) NOT NULL,
    source_type    VARCHAR(30) NOT NULL,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    rows_read      BIGINT NOT NULL DEFAULT 0,
    rows_valid     BIGINT NOT NULL DEFAULT 0,
    rows_inserted  BIGINT NOT NULL DEFAULT 0,
    rows_updated   BIGINT NOT NULL DEFAULT 0,
    rows_duplicate BIGINT NOT NULL DEFAULT 0,
    rows_rejected  BIGINT NOT NULL DEFAULT 0,
    status         VARCHAR(30) NOT NULL,
    error_summary  TEXT,
    CONSTRAINT ck_etl_status CHECK (status IN ('SUCCESS','PARTIAL_SUCCESS','FAILED'))
);

CREATE TABLE IF NOT EXISTS etl_row_errors (
    etl_error_id      BIGSERIAL PRIMARY KEY,
    etl_run_id        BIGINT NOT NULL REFERENCES etl_runs(etl_run_id) ON DELETE CASCADE,
    source_row_number BIGINT,
    field_name        VARCHAR(100),
    error_code        VARCHAR(100) NOT NULL,
    error_message     TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id      BIGSERIAL PRIMARY KEY,
    user_id       BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    action        VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id   VARCHAR(100),
    result        VARCHAR(30) NOT NULL DEFAULT 'SUCCESS',
    ip_address    INET,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_audit_result CHECK (result IN ('SUCCESS','FAILURE','DENIED'))
);

CREATE INDEX IF NOT EXISTS ix_candidates_full_name ON candidates(full_name);
CREATE INDEX IF NOT EXISTS ix_jobs_title_department ON jobs(job_title, department);
CREATE INDEX IF NOT EXISTS ix_applications_candidate_id ON applications(candidate_id);
CREATE INDEX IF NOT EXISTS ix_applications_job_id ON applications(job_id);
CREATE INDEX IF NOT EXISTS ix_applications_current_status ON applications(current_status);
CREATE INDEX IF NOT EXISTS ix_applications_applied_at ON applications(applied_at);
CREATE INDEX IF NOT EXISTS ix_stage_history_application_entered ON application_stage_history(application_id, entered_at);
CREATE INDEX IF NOT EXISTS ix_stage_history_stage_entered ON application_stage_history(stage_id, entered_at);
CREATE INDEX IF NOT EXISTS ix_ai_analysis_application_created ON ai_cv_analysis(application_id, created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS ix_etl_runs_started_status ON etl_runs(started_at, status);

-- Keep updated_at current for tables that expose it.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_candidates_updated_at ON candidates;
CREATE TRIGGER trg_candidates_updated_at BEFORE UPDATE ON candidates
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_applications_updated_at ON applications;
CREATE TRIGGER trg_applications_updated_at BEFORE UPDATE ON applications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
