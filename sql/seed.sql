-- Static catalogue seed for PostgreSQL.
-- Run after schema.sql. Full demo users/candidates are created by:
--   python scripts/init_db.py
-- (password hashes must be generated in Python, never hard-coded as plain text).

INSERT INTO roles (role_name, description) VALUES
    ('HR_MANAGER', 'Quản lý tuyển dụng, nhập dữ liệu, duyệt kết quả AI.'),
    ('HIRING_MANAGER', 'Quản lý tuyển dụng theo vị trí được giao, thêm nhận xét.'),
    ('ADMIN', 'Quản trị hệ thống, tài khoản và cấu hình.'),
    ('AUDITOR', 'Kiểm toán nhật ký, chỉ đọc.')
ON CONFLICT (role_name) DO NOTHING;

INSERT INTO stages (stage_name, stage_order, is_terminal) VALUES
    ('CV Screening', 1, FALSE),
    ('Online Test', 2, FALSE),
    ('Technical Interview', 3, FALSE),
    ('HR Interview', 4, FALSE),
    ('Offer', 5, FALSE),
    ('Hired', 6, TRUE)
ON CONFLICT (stage_name) DO NOTHING;
