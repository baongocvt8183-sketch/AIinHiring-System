from __future__ import annotations

import pytest
from sqlalchemy import select

from src.auth.permissions import PermissionDenied, get_scoped_application
from src.database.models import (
    Application,
    ApplicationNote,
    Candidate,
    Stage,
    User,
)
from src.database.queries import (
    add_application_note,
    archive_candidate,
    create_candidate,
    stage_history,
    update_application,
)


def _user(session, username):
    return session.scalar(select(User).where(User.username == username))


def _application(session, candidate_name):
    return session.scalar(
        select(Application)
        .join(Candidate, Candidate.candidate_id == Application.candidate_id)
        .where(Candidate.full_name == candidate_name)
        .limit(1)
    )


def test_hr_can_move_application_and_history_stays_synced(demo_session):
    hr = _user(demo_session, "hr")
    application = _application(demo_session, "Đinh Thị Nga")
    stages = {stage.stage_name: stage for stage in demo_session.scalars(select(Stage))}
    old_stage = application.current_stage_id

    updated = update_application(
        demo_session,
        user=hr,
        application=application,
        new_stage_id=stages["Online Test"].stage_id,
        new_status="IN_PROGRESS",
        result="PASSED",
        note="Đạt vòng sàng lọc.",
    )
    assert updated.current_stage_id == stages["Online Test"].stage_id
    assert updated.current_status == "IN_PROGRESS"

    histories = stage_history(demo_session, application.application_id)
    assert histories[-1].stage_id == stages["Online Test"].stage_id
    assert histories[-1].exited_at is None
    closed = [history for history in histories if history.stage_id == old_stage]
    assert closed and closed[-1].exited_at is not None
    assert closed[-1].result == "PASSED"


def test_hiring_manager_cannot_update_pipeline(demo_session):
    hm = _user(demo_session, "hiring")
    application = _application(demo_session, "Nguyễn Văn An")
    with pytest.raises(PermissionDenied):
        update_application(demo_session, user=hm, application=application, new_status="HIRED")


def test_hiring_manager_cannot_touch_out_of_scope_application(demo_session):
    hm = _user(demo_session, "hiring")
    backend_app = _application(demo_session, "Hoàng Văn Em")
    with pytest.raises(PermissionDenied):
        get_scoped_application(demo_session, hm, backend_app.application_id)


def test_hiring_manager_can_add_note_in_scope(demo_session):
    hm = _user(demo_session, "hiring")
    application = _application(demo_session, "Nguyễn Văn An")
    note = add_application_note(
        demo_session,
        user=hm,
        application=application,
        note_text="  Trao đổi thêm về kinh nghiệm NLP.  ",
        note_type="INTERVIEW",
    )
    assert note.note_text == "Trao đổi thêm về kinh nghiệm NLP."
    assert note.note_type == "INTERVIEW"
    notes = list(
        demo_session.scalars(select(ApplicationNote).where(ApplicationNote.application_id == application.application_id))
    )
    assert any(item.note_id == note.note_id for item in notes)


def test_archive_and_restore_candidate(demo_session):
    hr = _user(demo_session, "hr")
    candidate = demo_session.scalar(select(Candidate).where(Candidate.full_name == "Hồ Thị Tâm"))
    archive_candidate(demo_session, user=hr, candidate=candidate, archived=True)
    assert candidate.is_archived
    archive_candidate(demo_session, user=hr, candidate=candidate, archived=False)
    assert not candidate.is_archived


def test_create_candidate_rejects_duplicate_email(demo_session):
    hr = _user(demo_session, "hr")
    with pytest.raises(ValueError):
        create_candidate(
            demo_session,
            user=hr,
            full_name="Trùng Email",
            email="AN.NGUYEN@example.com",
            phone="0900000000",
        )
    with pytest.raises(ValueError):
        create_candidate(
            demo_session,
            user=hr,
            full_name="Sai Email",
            email="not-an-email",
            phone=None,
        )

    candidate = create_candidate(
        demo_session,
        user=hr,
        full_name="  Ứng Viên  Tạm  ",
        email="tam.ungvien@example.com",
        phone="090 123 4567",
    )
    assert candidate.full_name == "Ứng Viên Tạm"
    assert candidate.email == "tam.ungvien@example.com"
    assert candidate.phone == "0901234567"
    # Remove the temporary test candidate so later consistency tests are unaffected.
    demo_session.delete(candidate)
    demo_session.commit()
