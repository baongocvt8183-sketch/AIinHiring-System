# AIinHiring-System
projectofptthon
# Tiểu luận môn Lập trình Python, chọn bộ công nghệ:
Python + Streamlit + Pandas + PostgreSQL + SQLAlchemy + Plotly + PyMuPDF.
# Luồng xuyên suốt:
nhập dữ liệu → làm sạch → lưu kho dữ liệu → phân tích pipeline → xử lý CV → kiểm duyệt theo quyền.
# Xây dựng một ứng dụng Python có khả năng:
- Thu thập dữ liệu từ nhiều nguồn.
- Làm sạch và chuẩn hóa dữ liệu.
- Lưu trữ dữ liệu tập trung trong PostgreSQL.
- Theo dõi quá trình tuyển dụng của từng ứng viên.
- Phân tích hiệu quả tuyển dụng trên dashboard.
- Trích xuất thông tin từ CV bằng NLP.
- Đề xuất mức độ phù hợp giữa CV và mô tả công việc.
- Phân quyền truy cập và lưu nhật ký kiểm duyệt.
# ĐẶC TẢ DỰ ÁN: KHO DỮ LIỆU TUYỂN DỤNG CÓ AI PHÂN TÍCH PIPELINE ỨNG VIÊN

**Nhóm:** 11 -- AI 9\
**Mục đích tài liệu:** Mô tả yêu cầu, đặc tả chức năng, kiến trúc, luồng xử lý và thiết kế cơ sở dữ liệu cho dự án tiểu luận môn Lập trình Python.\
**Phiên bản:** 1.0\
**Ngôn ngữ triển khai đề xuất:** Python\
**Cơ sở dữ liệu:** PostgreSQL

---

## 1. Tổng quan dự án

### 1.1. Bối cảnh

Thông tin tuyển dụng thường được lưu rải rác trong CSV, Excel, API và CV PDF. Việc tổng hợp thủ công dễ gây trùng lặp dữ liệu, khó theo dõi lịch sử ứng tuyển, khó đo lường hiệu quả từng vòng tuyển dụng và tốn thời gian đọc CV. Dữ liệu ứng viên cũng cần được bảo vệ bằng cơ chế phân quyền và kiểm toán truy cập.

### 1.2. Mục tiêu

Xây dựng ứng dụng hỗ trợ phòng nhân sự:

1. Nhập dữ liệu từ CSV, Excel và API.
2. Làm sạch, chuẩn hóa, kiểm tra hợp lệ và phát hiện dữ liệu trùng.
3. Lưu dữ liệu tập trung trong PostgreSQL.
4. Theo dõi ứng viên, vị trí tuyển dụng, hồ sơ ứng tuyển và lịch sử các vòng tuyển dụng.
5. Hiển thị KPI và dashboard pipeline.
6. Trích xuất văn bản/kỹ năng từ CV PDF, tạo tóm tắt và đối chiếu kỹ năng với mô tả công việc.
7. Phân quyền HR Manager và Hiring Manager.
8. Che thông tin nhận dạng theo quyền truy cập và ghi nhật ký kiểm toán.
9. Theo dõi kết quả các lần nhập dữ liệu và phân tích CV.

### 1.3. Phạm vi MVP

**Bắt buộc trong bản đầu tiên:**

- Nhập CSV/Excel.
- ETL gồm Extract, Transform, Validate, Load.
- PostgreSQL với quan hệ khóa chính/khóa ngoại.
- Chống trùng ứng viên theo email đã chuẩn hóa khi email có giá trị.
- Quản lý vị trí, hồ sơ ứng tuyển, vòng tuyển dụng và lịch sử vòng.
- Dashboard có KPI, funnel, thời gian xử lý và bộ lọc.
- Trích xuất văn bản từ PDF có lớp văn bản; ghi nhận trường hợp cần OCR.
- Trích xuất kỹ năng bằng từ điển/regex và tính điểm khớp kỹ năng có giải thích.
- Hai vai trò người dùng và kiểm tra quyền phía máy chủ.
- Audit log cho hành động quan trọng.
- Dữ liệu mẫu giả lập và kiểm thử cơ bản.

**Có thể bổ sung sau:**

- Tích hợp API tuyển dụng thực tế.
- OCR cho CV dạng ảnh.
- Mô hình ngôn ngữ để tóm tắt CV.
- Phân quyền theo phòng ban/nhóm tuyển dụng chi tiết.
- Triển khai cloud, hàng đợi tác vụ hoặc xử lý hàng loạt lớn.

### 1.4. Ngoài phạm vi

- Tự động ra quyết định tuyển hoặc loại ứng viên mà không có HR kiểm duyệt.
- Huấn luyện mô hình AI từ đầu.
- Thu thập dữ liệu cá nhân từ nguồn không được phép.
- Đảm bảo tính chính xác tuyệt đối của dữ liệu trích xuất từ CV.

---

## 2. Người dùng và vai trò

### 2.1. HR Manager

Quyền đề xuất:

- Xem dashboard trong phạm vi được cấp.
- Nhập dữ liệu và xem lịch sử ETL.
- Quản lý ứng viên, vị trí và hồ sơ ứng tuyển.
- Xem CV và kết quả phân tích AI khi có quyền hợp lệ.
- Duyệt, từ chối hoặc yêu cầu chỉnh sửa kết quả AI.
- Thêm/chỉnh sửa nhận xét tuyển dụng theo quyền.
- Xem audit log nếu được cấp quyền kiểm toán.
- Quản lý tài khoản chỉ khi có quyền quản trị riêng.

### 2.2. Hiring Manager

Quyền đề xuất:

- Xem dashboard giới hạn theo vị trí/phạm vi được giao.
- Xem các hồ sơ ứng tuyển liên quan đến vị trí phụ trách.
- Xem kỹ năng, kinh nghiệm và kết quả phân tích được phép xem.
- Thêm nhận xét chuyên môn cho hồ sơ được giao.
- Không mặc định được quản lý tài khoản, xem toàn bộ dữ liệu hoặc xem audit log.

### 2.3. Nguyên tắc phân quyền

- Quyền phải được kiểm tra trong tầng nghiệp vụ/backend, không chỉ ẩn nút trên giao diện.
- Mặc định từ chối nếu không có quyền rõ ràng.
- Mỗi truy vấn hồ sơ phải kiểm tra cả quyền hành động và phạm vi tài nguyên.
- Không dùng tên, giới tính, ảnh hoặc đặc điểm được bảo vệ làm tiêu chí chấm điểm phù hợp.
- Điểm khớp kỹ năng chỉ hỗ trợ tham khảo; quyết định tuyển dụng cần có kiểm duyệt của con người.

---

## 3. Kiến trúc hệ thống

### 3.1. Công nghệ đề xuất

Thành phần Công nghệ Mục đích

---

Ngôn ngữ Python Logic ứng dụng UI Streamlit Dashboard và màn hình thao tác Xử lý dữ liệu Pandas CSV/Excel, làm sạch API client Requests Gọi API nguồn dữ liệu Database PostgreSQL Kho dữ liệu quan hệ Database access SQLAlchemy + psycopg ORM/kết nối DB PDF PyMuPDF Trích xuất văn bản OCR tùy chọn Tesseract hoặc dịch vụ OCR phù hợp CV dạng ảnh NLP MVP Regex + từ điển kỹ năng Trích xuất kỹ năng Biểu đồ Plotly Funnel, KPI, thời gian xử lý Kiểm thử Pytest Unit/integration tests Cấu hình Biến môi trường / `.env` Thông tin cấu hình

### 3.2. Sơ đồ luồng logic

```text
CSV / Excel / API
        |
        v
   ETL Pipeline
 Extract -> Transform -> Validate -> Deduplicate -> Load
        |
        v
    PostgreSQL <----------------------------+
        |                                    |
        +--> Dashboard / KPI / Funnel        |
        |                                    |
        +--> Quản lý hồ sơ ứng tuyển         |
        |                                    |
        +--> CV PDF -> Extract text -> NLP -> AI analysis
                                             |
                                             v
                                     HR review / approval

Authentication + RBAC + audit logging áp dụng xuyên suốt.
CV và tệp đầu vào được lưu trong vùng lưu trữ riêng, không công khai.
```

### 3.3. Cấu trúc thư mục khuyến nghị

```text
recruitment_ai_warehouse/
├── app.py
├── pages/
│   ├── 1_Overview.py
│   ├── 2_Data_Import.py
│   ├── 3_Recruitment_Pipeline.py
│   ├── 4_CV_Analysis.py
│   ├── 5_Candidate_Management.py
│   ├── 6_User_Management.py
│   └── 7_Audit_Logs.py
├── src/
│   ├── etl/
│   │   ├── extract.py
│   │   ├── transform.py
│   │   ├── validate.py
│   │   └── load.py
│   ├── database/
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── queries.py
│   ├── analytics/
│   │   ├── kpi.py
│   │   └── funnel.py
│   ├── cv_analysis/
│   │   ├── pdf_extractor.py
│   │   ├── skills_extractor.py
│   │   └── resume_matcher.py
│   ├── auth/
│   │   ├── authentication.py
│   │   └── permissions.py
│   └── audit/
│       └── audit_logger.py
├── sql/
│   ├── schema.sql
│   └── seed.sql
├── tests/
├── data/
│   └── sample/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 4. Đặc tả chức năng

### 4.1. T1 --- ETL và nhập dữ liệu

#### Đầu vào

- CSV.
- Excel `.xlsx`.
- API JSON (phần mở rộng).
- Thông tin nguồn và cấu hình ánh xạ cột.

#### Quy trình

 1. Kiểm tra quyền nhập dữ liệu.
 2. Kiểm tra loại tệp, kích thước và cấu trúc.
 3. Đọc dữ liệu nguồn.
 4. Ánh xạ tên cột nguồn về schema chuẩn.
 5. Chuẩn hóa chuỗi, email, ngày tháng và trạng thái.
 6. Kiểm tra trường bắt buộc và quy tắc hợp lệ.
 7. Phân loại bản ghi hợp lệ, không hợp lệ, trùng lặp.
 8. Nạp dữ liệu theo transaction phù hợp.
 9. Ghi thống kê và trạng thái vào `etl_runs`.
10. Hiển thị kết quả và lỗi có thể sửa.

#### Quy tắc chuẩn hóa

- Email: bỏ khoảng trắng đầu/cuối và chuyển chữ thường.
- Tên: bỏ khoảng trắng thừa; không tự ý thay đổi ý nghĩa tên.
- Ngày: chuẩn hóa về kiểu `DATE` hoặc `TIMESTAMPTZ` theo ý nghĩa cột.
- Trạng thái: ánh xạ giá trị nguồn về tập trạng thái được quy định.
- Bản ghi thiếu email không được tự động gộp chỉ vì email rỗng.
- Không xóa âm thầm bản ghi lỗi; cần báo số lượng và lý do loại.
- Khi cập nhật dữ liệu đã có, phải quy định trường nào được cập nhật và lưu log.

#### Kết quả ETL cần hiển thị

- Tên nguồn.
- Thời điểm bắt đầu/kết thúc.
- Tổng dòng đọc.
- Số bản ghi hợp lệ.
- Số bản ghi tạo mới.
- Số bản ghi cập nhật.
- Số bản ghi trùng.
- Số bản ghi bị từ chối.
- Lỗi theo dòng hoặc theo trường.
- Trạng thái `SUCCESS`, `PARTIAL_SUCCESS` hoặc `FAILED`.

### 4.2. T2 --- Chuẩn hóa dữ liệu và kho dữ liệu

- Ứng viên tách biệt với hồ sơ ứng tuyển.
- Một ứng viên có thể có nhiều hồ sơ ứng tuyển.
- Một vị trí có thể nhận nhiều hồ sơ.
- Một hồ sơ có lịch sử đi qua nhiều vòng.
- Lưu lịch sử vòng thay vì chỉ lưu trạng thái hiện tại.
- Kết quả AI lưu riêng và gắn với hồ sơ ứng tuyển.
- Nhật ký ETL và audit log là các thực thể độc lập.
- Sử dụng khóa chính, khóa ngoại, ràng buộc `UNIQUE`, `CHECK` và chỉ mục phù hợp.

### 4.3. T3 --- Dashboard pipeline

#### KPI

- Tổng số hồ sơ ứng tuyển trong bộ lọc.
- Số hồ sơ đang xử lý.
- Số hồ sơ đã tuyển.
- Tỷ lệ chuyển đổi giữa các vòng.
- Thời gian xử lý trung bình theo vòng.
- Thời gian tuyển dụng trung bình.
- Số hồ sơ theo vị trí và nguồn tuyển dụng.

#### Biểu đồ

- Funnel theo vòng tuyển dụng.
- Biểu đồ số lượng theo trạng thái.
- Biểu đồ thời gian xử lý theo vòng.
- Biểu đồ hồ sơ theo vị trí/phòng ban.
- Bảng chi tiết hồ sơ theo bộ lọc.

#### Bộ lọc

- Khoảng thời gian.
- Vị trí tuyển dụng.
- Phòng ban.
- Nguồn ứng viên.
- Trạng thái hồ sơ.

#### Quy tắc đo lường

- Funnel phải tính theo hồ sơ đã đi vào từng vòng, không lấy số trạng thái hiện tại để thay thế lịch sử.
- Tỷ lệ chuyển đổi vòng N sang N+1 = số hồ sơ thuộc cohort đi vào N+1 / số hồ sơ thuộc cohort đi vào N × 100%.
- Nếu mẫu số bằng 0, hiển thị `N/A` hoặc 0 theo quy ước nhất quán.
- Thời gian một vòng = thời điểm ra vòng trừ thời điểm vào vòng.
- Hồ sơ chưa ra vòng cần được hiển thị riêng là thời gian chờ hiện tại, không trộn với thời gian hoàn tất.
- Phải mô tả rõ khoảng thời gian và cách xử lý hồ sơ rút/loại để tránh so sánh sai.

### 4.4. T4 --- NLP/AI xử lý CV

#### Quy trình

 1. Người dùng có quyền tải CV PDF lên.
 2. Kiểm tra loại tệp, kích thước và nội dung tệp.
 3. Lưu tệp trong vùng riêng tư với mã định danh ngẫu nhiên.
 4. Trích xuất văn bản bằng PyMuPDF.
 5. Nếu không có văn bản, đánh dấu cần OCR hoặc báo lỗi phù hợp.
 6. Chuẩn hóa văn bản và nhận diện kỹ năng bằng từ điển/regex.
 7. Lấy yêu cầu kỹ năng từ vị trí tuyển dụng.
 8. Tính điểm khớp kỹ năng có thể giải thích.
 9. Tạo bản tóm tắt nếu có mô-đun AI.
10. Lưu kết quả, phiên bản phương pháp/mô hình và thời gian phân tích.
11. Chuyển kết quả cho HR kiểm duyệt.
12. Ghi audit log khi xem, duyệt hoặc yêu cầu sửa.

#### Công thức điểm khớp kỹ năng MVP

`skill_match_score = số kỹ năng yêu cầu được tìm thấy / tổng số kỹ năng yêu cầu * 100`

- Nếu vị trí không có kỹ năng yêu cầu, điểm phải là `NULL` hoặc trạng thái `NOT_SCORABLE`, không tự động coi là 100%.
- Điểm chỉ phản ánh độ khớp của danh sách kỹ năng đã cấu hình.
- Không gọi điểm này là xác suất trúng tuyển.
- Không dùng giới tính, tuổi, ảnh, tên hoặc đặc điểm được bảo vệ làm tiêu chí chấm điểm.
- HR có thể duyệt, từ chối hoặc yêu cầu chỉnh sửa; hệ thống phải lưu quyết định và người thực hiện.
- Nội dung CV có thể chứa dữ liệu cá nhân; không gửi cho dịch vụ AI bên ngoài nếu chưa đánh giá quyền riêng tư và cấu hình phù hợp.

#### Trạng thái phân tích đề xuất

`PENDING`, `PROCESSING`, `SUCCESS`, `FAILED`, `NEEDS_OCR`, `REVIEW_REQUIRED`, `APPROVED`, `REJECTED`, `REVISION_REQUESTED`.

Có thể tách trạng thái xử lý kỹ thuật và trạng thái kiểm duyệt thành hai trường riêng để tránh một cột trạng thái quá phức tạp.

### 4.5. T5 --- RBAC, bảo mật và audit

#### Các chức năng

- Đăng nhập/đăng xuất.
- Băm mật khẩu bằng thư viện phù hợp; không lưu mật khẩu thuần.
- Phân quyền theo vai trò.
- Kiểm tra quyền xem/sửa trên backend.
- Giới hạn hồ sơ theo vị trí hoặc phạm vi được giao.
- Che dữ liệu nhạy cảm theo quyền.
- Ghi nhật ký các hành động quan trọng.
- Quản lý bí mật bằng biến môi trường.
- Kiểm tra quyền tải xuống và xem CV.
- Lưu người duyệt, thời điểm duyệt, kết quả và ghi chú.

#### Hành động cần ghi audit

- Đăng nhập thành công/thất bại (không ghi mật khẩu).
- Nhập dữ liệu.
- Xem hoặc tải CV nếu chính sách yêu cầu.
- Xem kết quả AI.
- Duyệt/từ chối/yêu cầu sửa kết quả AI.
- Thay đổi trạng thái hồ sơ.
- Thay đổi quyền người dùng.
- Truy cập bị từ chối đối với tài nguyên quan trọng.

Không ghi toàn bộ CV, mật khẩu, token hoặc thông tin cá nhân không cần thiết vào log.

---

## 5. Thiết kế cơ sở dữ liệu PostgreSQL

### 5.1. Nguyên tắc thiết kế

- Dùng `BIGSERIAL` hoặc `GENERATED ... AS IDENTITY` cho khóa số; UUID có thể dùng cho ID công khai.
- Dùng `TIMESTAMPTZ` cho thời điểm có ý nghĩa thời gian toàn hệ thống.
- Dùng `DATE` cho ngày không cần thời gian.
- Dùng `NUMERIC` cho điểm số nếu cần độ chính xác thập phân.
- Dùng `JSONB` chỉ cho dữ liệu bán cấu trúc; các quan hệ cốt lõi nên là bảng quan hệ.
- Dùng khóa ngoại để bảo đảm tính toàn vẹn.
- Quy định hành vi xóa; ưu tiên lưu trữ/ẩn hoặc `RESTRICT` cho dữ liệu cần kiểm toán.
- Không đặt CV, email, số điện thoại hoặc thông tin nhạy cảm vào audit log.
- Dữ liệu mẫu dùng trong demo phải là dữ liệu giả lập.

### 5.2. Danh sách bảng

---

Bảng Mục đích Quan hệ chính

---

`users` Tài khoản người dùng Liên kết với role/audit/review

`roles` Danh mục vai trò Một role có nhiều user

`user_roles` Gán vai trò cho user Bảng nối user-role

`candidates` Thông tin ứng viên Một candidate có nhiều application

`jobs` Vị trí tuyển dụng Một job có nhiều application

`stages` Danh mục vòng tuyển Một stage có nhiều dụng history

`applications` Hồ sơ ứng tuyển Nối candidate và job

`application_stage_history` Lịch sử đi qua các vòng Nhiều dòng cho một application

`job_required_skills` Kỹ năng yêu cầu của vị Nối job với kỹ năng trí

`candidate_documents` Metadata tệp CV Nối candidate hoặc application

`ai_cv_analysis` Kết quả phân tích CV Nhiều lần phân tích cho application

`ai_analysis_reviews` Lịch sử HR kiểm duyệt Gắn với một lần phân tích

`etl_runs` Lịch sử các lần ETL Độc lập, ghi thống kê nguồn

`etl_row_errors` Lỗi theo dòng nhập Nhiều lỗi thuộc một ETL run

`audit_logs` Nhật ký hoạt động Có thể tham chiếu user

## `application_notes` Nhận xét tuyển dụng Gắn application và người tạo

### 5.3. ERD logic dạng văn bản

```text
roles 1 --- N user_roles N --- 1 users
users 1 --- N audit_logs

candidates 1 --- N applications N --- 1 jobs
applications 1 --- N application_stage_history N --- 1 stages
jobs 1 --- N job_required_skills
candidates 1 --- N candidate_documents
applications 1 --- N ai_cv_analysis
ai_cv_analysis 1 --- N ai_analysis_reviews
applications 1 --- N application_notes

etl_runs 1 --- N etl_row_errors
```

### 5.4. Định nghĩa bảng chi tiết

#### `roles`

Cột Kiểu Ràng buộc Ý nghĩa

---

`role_id` BIGINT PK Mã vai trò `role_name` VARCHAR(50) UNIQUE, NOT NULL Tên vai trò `description` TEXT NULL Mô tả

Dữ liệu khởi tạo: `HR_MANAGER`, `HIRING_MANAGER`, có thể thêm `ADMIN` và `AUDITOR` khi cần.

#### `users`

Cột Kiểu Ràng buộc Ý nghĩa

---

`user_id` BIGINT PK Mã người dùng `username` VARCHAR(100) UNIQUE, NOT NULL Tên đăng nhập `email` VARCHAR(255) UNIQUE, NOT NULL Email tài khoản `password_hash` TEXT NOT NULL Hash mật khẩu `full_name` VARCHAR(200) NOT NULL Tên hiển thị `is_active` BOOLEAN NOT NULL DEFAULT TRUE Trạng thái tài khoản `created_at` TIMESTAMPTZ NOT NULL Thời điểm tạo `updated_at` TIMESTAMPTZ NOT NULL Thời điểm cập nhật

#### `user_roles`

Cột Kiểu Ràng buộc Ý nghĩa

---

`user_id` BIGINT PK, FK users Người dùng `role_id` BIGINT PK, FK roles Vai trò `assigned_at` TIMESTAMPTZ NOT NULL Thời điểm gán `assigned_by` BIGINT FK users, NULL Người gán

Khóa chính ghép `(user_id, role_id)`.

#### `candidates`

Cột Kiểu Ràng buộc Ý nghĩa

---

`candidate_id` BIGINT PK Mã ứng viên `full_name` VARCHAR(200) NOT NULL Họ tên `email` VARCHAR(255) NULL Email chuẩn hóa `phone` VARCHAR(50) NULL Số điện thoại `created_at` TIMESTAMPTZ NOT NULL Thời điểm tạo `updated_at` TIMESTAMPTZ NOT NULL Thời điểm cập nhật `is_archived` BOOLEAN NOT NULL DEFAULT FALSE Cờ lưu trữ

Quy tắc: email nếu có giá trị phải được chuẩn hóa trước khi lưu. Có thể tạo unique index trên `lower(email)` hoặc bảo đảm lưu email chuẩn hóa và tạo unique constraint. Không áp dụng uniqueness cho giá trị email rỗng; trong PostgreSQL, nhiều giá trị `NULL` được phép trong unique constraint thông thường.

#### `jobs`

Cột Kiểu Ràng buộc Ý nghĩa

---

`job_id` BIGINT PK Mã vị trí `job_title` VARCHAR(200) NOT NULL Tên vị trí `department` VARCHAR(150) NULL Phòng ban `job_description` TEXT NULL Mô tả công việc `source_name` VARCHAR(100) NULL Nguồn dữ liệu nếu có `is_active` BOOLEAN NOT NULL DEFAULT TRUE Còn tuyển hay không `created_at` TIMESTAMPTZ NOT NULL Thời điểm tạo

#### `stages`

---

Cột Kiểu Ràng buộc Ý nghĩa

---

`stage_id` BIGINT PK Mã vòng

`stage_name` VARCHAR(100) UNIQUE, NOT NULL Tên vòng

`stage_order` INTEGER UNIQUE, NOT NULL Thứ tự chuẩn

## `is_terminal` BOOLEAN NOT NULL DEFAULT Có phải trạng FALSE thái kết thúc quy trình hay không

Danh mục mẫu: `CV Screening`, `Online Test`, `Technical Interview`, `HR Interview`, `Offer`, `Hired`. Trạng thái bị loại/rút hồ sơ có thể được quản lý bằng trường trạng thái kết thúc riêng hoặc stage kết thúc theo quy ước rõ ràng. Không trộn lẫn stage và trạng thái ứng tuyển mà không có định nghĩa.

#### `applications`

Cột Kiểu Ràng buộc Ý nghĩa

---

`application_id` BIGINT PK Mã hồ sơ ứng tuyển `candidate_id` BIGINT FK candidates, NOT NULL Ứng viên `job_id` BIGINT FK jobs, NOT NULL Vị trí ứng tuyển `applied_at` TIMESTAMPTZ NOT NULL Thời điểm ứng tuyển `current_stage_id` BIGINT FK stages, NULL Vòng hiện tại `current_status` VARCHAR(30) NOT NULL Trạng thái tổng thể `source_name` VARCHAR(100) NULL Nguồn ứng viên `created_at` TIMESTAMPTZ NOT NULL Thời điểm tạo `updated_at` TIMESTAMPTZ NOT NULL Thời điểm cập nhật

Trạng thái đề xuất: `IN_PROGRESS`, `HIRED`, `REJECTED`, `WITHDRAWN`, `OFFER_DECLINED`, `ON_HOLD`. Dùng `CHECK` constraint hoặc bảng danh mục để giới hạn giá trị hợp lệ.

Có thể đặt `UNIQUE(candidate_id, job_id)` nếu nghiệp vụ chỉ cho phép một hồ sơ cho mỗi ứng viên/vị trí. Nếu cho phép ứng tuyển lại nhiều lần, không dùng ràng buộc này; thay bằng mã lần ứng tuyển hoặc quy tắc khác.

#### `application_stage_history`

Cột Kiểu Ràng buộc Ý nghĩa

---

`history_id` BIGINT PK Mã lịch sử `application_id` BIGINT FK applications, NOT NULL Hồ sơ `stage_id` BIGINT FK stages, NOT NULL Vòng `entered_at` TIMESTAMPTZ NOT NULL Thời điểm vào vòng `exited_at` TIMESTAMPTZ NULL Thời điểm rời vòng `result` VARCHAR(30) NULL Kết quả vòng `notes` TEXT NULL Ghi chú không nhạy cảm

`result` có thể gồm `PASSED`, `FAILED`, `PENDING`, `SKIPPED`. Ràng buộc kiểm tra: `exited_at IS NULL OR exited_at >= entered_at`. Cần bảo đảm quy trình nghiệp vụ không tạo nhiều vòng đang mở không hợp lệ cho cùng hồ sơ.

#### `job_required_skills`

---

Cột Kiểu Ràng buộc Ý nghĩa

---

`job_id` BIGINT PK, FK jobs Vị trí

`skill_name` VARCHAR(100) PK Tên kỹ năng chuẩn hóa

`importance` NUMERIC(4,3) NOT NULL DEFAULT Trọng số 0--1 1.0

## `is_required` BOOLEAN NOT NULL DEFAULT Kỹ năng bắt buộc TRUE hay ưu tiên

Ràng buộc `importance >= 0 AND importance <= 1`. Khóa chính ghép `(job_id, skill_name)`.

#### `candidate_documents`

---

Cột Kiểu Ràng buộc Ý nghĩa

---

`document_id` BIGINT PK Mã tài liệu

`candidate_id` BIGINT FK candidates, Ứng viên NOT NULL

`application_id` BIGINT FK applications, Hồ sơ liên quan NULL

`storage_key` TEXT UNIQUE, NOT NULL Khóa tệp trong vùng lưu trữ riêng

`original_filename` VARCHAR(255) NOT NULL Tên file gốc đã kiểm tra

`mime_type` VARCHAR(100) NOT NULL Loại nội dung

`file_size_bytes` BIGINT NOT NULL Kích thước

`sha256_hash` CHAR(64) NULL Hash kiểm tra tệp

`uploaded_by` BIGINT FK users, NULL Người tải lên

## `uploaded_at` TIMESTAMPTZ NOT NULL Thời điểm tải lên

Không lưu file CV vào thư mục public. Cần kiểm tra loại file, kích thước, tên tệp, quyền truy cập và chính sách lưu trữ/xóa dữ liệu.

#### `ai_cv_analysis`

---

Cột Kiểu Ràng buộc Ý nghĩa

---

`analysis_id` BIGINT PK Mã lần phân tích

`application_id` BIGINT FK applications, NOT Hồ sơ NULL

`document_id` BIGINT FK CV được phân tích candidate_documents,\
NULL

`skills_extracted` JSONB NOT NULL DEFAULT `[]` Danh sách kỹ năng

`experience_summary` TEXT NULL Tóm tắt kinh nghiệm

`projects_summary` TEXT NULL Tóm tắt dự án

`skill_match_score` NUMERIC(5,2) NULL Điểm khớp kỹ năng 0--100

`missing_skills` JSONB NOT NULL DEFAULT `[]` Kỹ năng chưa tìm thấy

`processing_status` VARCHAR(30) NOT NULL Trạng thái xử lý

`review_status` VARCHAR(30) NOT NULL Trạng thái kiểm duyệt

`method_version` VARCHAR(100) NULL Phiên bản thuật toán/mô hình

## `created_at` TIMESTAMPTZ NOT NULL Thời điểm tạo

Kiểm tra `skill_match_score IS NULL OR (skill_match_score >= 0 AND skill_match_score <= 100)`. Nên tách `processing_status` và `review_status`, ví dụ review status: `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `REVISION_REQUESTED`.

#### `ai_analysis_reviews`

---

Cột Kiểu Ràng buộc Ý nghĩa

---

`review_id` BIGINT PK Mã lần kiểm duyệt

`analysis_id` BIGINT FK Kết quả phân tích ai_cv_analysis,\
NOT NULL

`reviewer_id` BIGINT FK users, NOT Người kiểm duyệt NULL

`decision` VARCHAR(30) NOT NULL Quyết định

`review_note` TEXT NULL Ghi chú

## `created_at` TIMESTAMPTZ NOT NULL Thời điểm

Quyết định: `APPROVED`, `REJECTED`, `REVISION_REQUESTED`. Mỗi lần kiểm duyệt là một dòng lịch sử; không chỉ ghi đè quyết định cũ.

#### `application_notes`

Cột Kiểu Ràng buộc Ý nghĩa

---

`note_id` BIGINT PK Mã nhận xét `application_id` BIGINT FK applications, NOT NULL Hồ sơ `author_id` BIGINT FK users, NOT NULL Người tạo `note_type` VARCHAR(30) NOT NULL Loại nhận xét `note_text` TEXT NOT NULL Nội dung `created_at` TIMESTAMPTZ NOT NULL Thời điểm

Quyền đọc/ghi nhận xét phải được kiểm soát. Tránh ghi nhận xét mang tính phân biệt đối xử hoặc thông tin không liên quan đến công việc.

#### `etl_runs`

Cột Kiểu Ràng buộc Ý nghĩa

---

`etl_run_id` BIGINT PK Mã lần chạy `source_name` VARCHAR(255) NOT NULL Tên nguồn `source_type` VARCHAR(30) NOT NULL CSV, EXCEL, API `started_at` TIMESTAMPTZ NOT NULL Bắt đầu `finished_at` TIMESTAMPTZ NULL Kết thúc `rows_read` BIGINT NOT NULL DEFAULT 0 Dòng đã đọc `rows_valid` BIGINT NOT NULL DEFAULT 0 Dòng hợp lệ `rows_inserted` BIGINT NOT NULL DEFAULT 0 Dòng tạo mới `rows_updated` BIGINT NOT NULL DEFAULT 0 Dòng cập nhật `rows_duplicate` BIGINT NOT NULL DEFAULT 0 Dòng trùng `rows_rejected` BIGINT NOT NULL DEFAULT 0 Dòng bị từ chối `status` VARCHAR(30) NOT NULL Trạng thái `error_summary` TEXT NULL Tóm tắt lỗi

#### `etl_row_errors`

Cột Kiểu Ràng buộc Ý nghĩa

---

`etl_error_id` BIGINT PK Mã lỗi `etl_run_id` BIGINT FK etl_runs, NOT NULL Lần ETL `source_row_number` BIGINT NULL Số dòng nguồn `field_name` VARCHAR(100) NULL Trường lỗi `error_code` VARCHAR(100) NOT NULL Mã lỗi `error_message` TEXT NOT NULL Mô tả lỗi `created_at` TIMESTAMPTZ NOT NULL Thời điểm

Không lưu toàn bộ dòng nguồn nếu dòng đó chứa dữ liệu cá nhân. Chỉ lưu thông tin lỗi tối thiểu cần thiết.

#### `audit_logs`

---

Cột Kiểu Ràng buộc Ý nghĩa

---

`audit_id` BIGINT PK Mã nhật ký

`user_id` BIGINT FK users, NULL Người thực hiện; NULL nếu chưa xác định

`action` VARCHAR(100) NOT NULL Hành động

`resource_type` VARCHAR(100) NULL Loại tài nguyên

`resource_id` VARCHAR(100) NULL Mã tài nguyên

`result` VARCHAR(30) NOT NULL SUCCESS/FAILURE/DENIED

`ip_address` INET NULL Địa chỉ IP nếu chính sách cho phép

`metadata` JSONB NOT NULL DEFAULT Metadata tối thiểu `{}`

## `created_at` TIMESTAMPTZ NOT NULL Thời điểm

Audit log nên được bảo vệ khỏi chỉnh sửa tùy tiện. Không lưu mật khẩu, token, toàn văn CV hoặc thông tin nhạy cảm trong `metadata`.

---

## 6. Chỉ mục và ràng buộc cơ sở dữ liệu

Chỉ mục đề xuất:

- `candidates(email)` với quy tắc uniqueness phù hợp cho email không NULL.
- `applications(candidate_id)`.
- `applications(job_id)`.
- `applications(current_status)`.
- `applications(applied_at)`.
- `application_stage_history(application_id, entered_at)`.
- `application_stage_history(stage_id, entered_at)`.
- `ai_cv_analysis(application_id, created_at)`.
- `audit_logs(created_at)`.
- `etl_runs(started_at, status)`.

Không tạo chỉ mục cho mọi cột một cách máy móc; cần cân nhắc các truy vấn thường dùng và chi phí ghi dữ liệu.

Các ràng buộc cần cân nhắc:

- Email chuẩn hóa và unique khi không NULL.
- Khóa ngoại cho mọi quan hệ chính.
- `CHECK` cho trạng thái, điểm số, thời gian và trọng số.
- Transaction cho thao tác nạp dữ liệu liên quan nhiều bảng.
- Quy tắc xóa rõ ràng; tránh cascade xóa mất lịch sử kiểm toán.
- Quy tắc xử lý cập nhật trùng lặp phải xác định trước.

---

## 7. Truy vấn SQL mẫu cho dashboard

### 7.1. Số hồ sơ theo trạng thái

```sql
SELECT current_status, COUNT(*) AS total_applications
FROM applications
GROUP BY current_status
ORDER BY total_applications DESC;
```

### 7.2. Số hồ sơ theo vị trí

```sql
SELECT
    j.job_title,
    COUNT(a.application_id) AS total_applications
FROM jobs AS j
LEFT JOIN applications AS a ON a.job_id = j.job_id
GROUP BY j.job_id, j.job_title
ORDER BY total_applications DESC;
```

### 7.3. Lịch sử vòng tuyển dụng của một hồ sơ

```sql
SELECT
    a.application_id,
    s.stage_name,
    h.entered_at,
    h.exited_at,
    h.result
FROM application_stage_history AS h
JOIN applications AS a ON a.application_id = h.application_id
JOIN stages AS s ON s.stage_id = h.stage_id
WHERE a.application_id = :application_id
ORDER BY h.entered_at;
```

`:application_id` phải được truyền bằng tham số của thư viện database; không nối trực tiếp giá trị người dùng vào chuỗi SQL.

### 7.4. Thời gian hoàn tất theo vòng

```sql
SELECT
    s.stage_name,
    AVG(EXTRACT(EPOCH FROM (h.exited_at - h.entered_at)) / 86400.0)
        AS avg_days
FROM application_stage_history AS h
JOIN stages AS s ON s.stage_id = h.stage_id
WHERE h.exited_at IS NOT NULL
GROUP BY s.stage_id, s.stage_name, s.stage_order
ORDER BY s.stage_order;
```

Truy vấn này tính trung bình cho các lượt đã kết thúc. Cần bổ sung bộ lọc ngày/vị trí theo dashboard khi triển khai.

### 7.5. Ví dụ tính tỷ lệ chuyển đổi

Tỷ lệ chuyển đổi nên được tính từ lịch sử hồ sơ trong cùng phạm vi thống kê. Với dữ liệu đơn giản, nhóm có thể đếm số `application_id` khác nhau đã đi vào từng stage, sau đó chia số hồ sơ ở stage sau cho số hồ sơ ở stage trước. Cần thống nhất cách xử lý hồ sơ quay lại vòng, bỏ qua vòng, rút hồ sơ và thời gian cohort.

---

## 8. Quy tắc nghiệp vụ quan trọng

 1. Mỗi ứng viên có một `candidate_id` ổn định.
 2. Một ứng viên có thể có nhiều hồ sơ ứng tuyển.
 3. Mỗi hồ sơ thuộc một vị trí tuyển dụng.
 4. Lịch sử vòng được lưu thành các sự kiện có thời điểm.
 5. Trạng thái hiện tại trong `applications` cần đồng bộ với lịch sử.
 6. Không gộp ứng viên chỉ dựa trên tên.
 7. Không tự động gộp dòng thiếu email.
 8. Mọi thay đổi quan trọng phải có thể truy vết.
 9. Điểm AI phải đi kèm phiên bản phương pháp và thời gian tạo.
10. AI không tự ra quyết định tuyển dụng cuối cùng.
11. Dữ liệu cá nhân chỉ được hiển thị theo quyền và mục đích hợp lệ.
12. Các số liệu dashboard phải có định nghĩa rõ ràng.
13. Dữ liệu demo phải giả lập và nhất quán giữa các bảng.
14. Thông tin kết nối DB và API key không được commit vào kho mã nguồn.

---

## 9. Yêu cầu phi chức năng

### 9.1. Bảo mật

- Xác thực người dùng.
- Hash mật khẩu bằng thư viện chuyên dụng.
- Kiểm tra RBAC ở tầng nghiệp vụ.
- Sử dụng truy vấn tham số/ORM.
- Kiểm tra file tải lên.
- Lưu CV trong vùng không công khai.
- Quản lý bí mật qua biến môi trường.
- Hạn chế thông tin nhạy cảm trong log.
- Quy định thời hạn lưu trữ và xóa dữ liệu.

### 9.2. Tính đúng đắn dữ liệu

- Có kiểm tra schema đầu vào.
- Có ràng buộc khóa chính/ngoại.
- Có xử lý transaction.
- Có log số dòng đọc, tạo, cập nhật và từ chối.
- Có khả năng tái chạy ETL mà không tạo dữ liệu trùng không mong muốn.

### 9.3. Khả năng sử dụng

- Giao diện có nhãn rõ ràng.
- Có thông báo thành công/thất bại.
- Có trạng thái đang xử lý.
- Có bộ lọc và thông báo khi không có dữ liệu.
- Có phân trang cho bảng lớn.
- Không hiển thị thông tin nhận dạng cho người dùng không có quyền.

### 9.4. Khả năng bảo trì

- Tách UI, nghiệp vụ, ETL và truy vấn DB.
- Dùng cấu hình môi trường.
- Có `requirements.txt`.
- Có tài liệu khởi chạy.
- Có kiểm thử các chức năng quan trọng.

---

## 10. Kế hoạch kiểm thử và tiêu chí nghiệm thu

---

Mã Kiểm thử Kết quả mong đợi

---

TC-01 Nhập CSV hợp lệ Dữ liệu được nạp đúng

TC-02 Nhập Excel hợp lệ Dữ liệu được nạp đúng

TC-03 Email trùng sau chuẩn Không tạo ứng viên hóa trùng

TC-04 Dòng thiếu trường bắt Bị từ chối và ghi lý do buộc

TC-05 Chạy ETL lại cùng nguồn Không tạo trùng ngoài quy tắc

TC-06 Truy vấn số hồ sơ theo Số liệu khớp dữ liệu DB trạng thái

TC-07 Tính thời gian vòng đã Kết quả khớp timestamp kết thúc

TC-08 PDF có văn bản Trích xuất được nội dung

TC-09 PDF dạng ảnh Báo cần OCR hoặc xử lý theo cấu hình

TC-10 CV có kỹ năng trong từ Kỹ năng được trích xuất điển

TC-11 Vị trí không có kỹ năng Điểm khớp là yêu cầu NULL/NOT_SCORABLE

TC-12 Hiring Manager truy cập Bị từ chối ở backend ngoài phạm vi

TC-13 Người dùng không quyền Không thể duyệt duyệt AI

TC-14 HR duyệt kết quả AI Có bản ghi review và audit

TC-15 Xem audit log Chỉ người có quyền được xem

## TC-16 Tệp sai định dạng Bị từ chối an toàn

### Tiêu chí nghiệm thu MVP

- Có thể chạy ứng dụng từ hướng dẫn trong README.
- Cơ sở dữ liệu được tạo từ schema.
- Có dữ liệu mẫu nhất quán.
- ETL chạy được với CSV/Excel mẫu.
- Dashboard hiển thị số liệu truy vấn từ PostgreSQL.
- CV PDF được trích xuất và phân tích kỹ năng.
- Có hai vai trò với quyền khác nhau.
- Quyền được kiểm tra phía backend.
- Có audit log cho các hành động quan trọng.
- Các kiểm thử cốt lõi đều chạy và có kết quả rõ ràng.

---

## 11. Gợi ý thứ tự triển khai

### Giai đoạn 1 --- Nền tảng dữ liệu

1. Tạo repository và môi trường Python.
2. Tạo PostgreSQL.
3. Tạo schema và dữ liệu mẫu.
4. Xây dựng ETL CSV/Excel.
5. Kiểm thử chuẩn hóa và chống trùng.

### Giai đoạn 2 --- Dashboard

1. Viết truy vấn KPI.
2. Tạo trang tổng quan.
3. Tạo funnel.
4. Tạo biểu đồ thời gian xử lý.
5. Thêm bộ lọc và bảng chi tiết.

### Giai đoạn 3 --- CV/NLP

1. Upload PDF an toàn.
2. Trích xuất văn bản.
3. Trích xuất kỹ năng.
4. Đối chiếu kỹ năng theo vị trí.
5. Lưu kết quả và lịch sử phân tích.
6. Bổ sung AI tóm tắt nếu đủ thời gian.

### Giai đoạn 4 --- Bảo mật và tích hợp

1. Xây dựng đăng nhập.
2. Xây dựng RBAC.
3. Kiểm tra quyền truy cập từng hồ sơ.
4. Ghi audit log.
5. Kiểm thử quyền.
6. Tích hợp toàn bộ luồng và tập dượt demo.

---

## 12. Nội dung cần thể hiện khi bảo vệ

- **T1:** Sơ đồ ETL, log thực tế và số dòng đã nạp.
- **T2:** ERD, ràng buộc khóa ngoại và truy vấn tổng hợp.
- **T3:** Dashboard với KPI, funnel và thời gian xử lý.
- **T4:** CV mẫu, văn bản trích xuất, kỹ năng và kết quả đối chiếu.
- **T5:** Ma trận quyền, thử truy cập trái phép và audit log.

Kịch bản demo xuyên suốt:

1. Nhập file CSV/Excel.
2. Xem log ETL và dữ liệu trong PostgreSQL.
3. Mở dashboard để xem số liệu.
4. Tải CV mẫu lên và chạy phân tích.
5. HR kiểm duyệt kết quả.
6. Đăng nhập bằng Hiring Manager và chứng minh quyền bị giới hạn.
7. Xem audit log bằng tài khoản được cấp quyền.

---

## 13. Các quyết định cần chốt trước khi code

 1. Có cho phép một ứng viên ứng tuyển lại cùng một vị trí hay không.
 2. Email có bắt buộc không; cách xử lý ứng viên không có email.
 3. Quy tắc đồng bộ `current_status` với lịch sử vòng.
 4. Các trạng thái cuối: hired, rejected, withdrawn, offer declined.
 5. Định nghĩa chính xác KPI và funnel.
 6. CV được lưu trên ổ đĩa riêng hay object storage.
 7. Có dùng API AI bên ngoài hay chỉ xử lý cục bộ.
 8. Phạm vi dữ liệu Hiring Manager được xem.
 9. Thời hạn lưu trữ CV và nhật ký.
10. Phân chia module và giao diện dữ liệu giữa các thành viên.

---

## 14. Kết luận

Dự án cần được xây dựng như một hệ thống thống nhất, không phải năm chức năng độc lập. PostgreSQL là nền tảng dữ liệu; ETL đưa dữ liệu về cấu trúc chuẩn; dashboard khai thác dữ liệu lịch sử; NLP/AI hỗ trợ phân tích CV; RBAC và audit log bảo vệ dữ liệu và giúp truy vết hoạt động.

Để hoàn thành tiểu luận đúng hạn, hãy ưu tiên phiên bản MVP có thể chạy xuyên suốt từ nhập dữ liệu đến dashboard, phân tích CV và kiểm tra phân quyền. Chỉ bổ sung mô hình AI phức tạp hoặc tích hợp API ngoài sau khi các phần cốt lõi hoạt động ổn định.
