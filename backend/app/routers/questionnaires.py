"""
Questionnaire upload + inspection endpoints.

The upload flow is the first place where parsing (app/parsing.py) and
matching (app/routers/matching.py::match_single_question) actually meet:
upload a file → extract questions → match every question → store one
questionnaire_items row per question with its match + confidence bucket,
so a human can review them afterwards.
"""
import os
import tempfile
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.database import get_db
from app.models import (
    QuestionnaireItemOut,
    QuestionnaireItemUpdate,
    QuestionnaireUploadResponse,
)
from app.parsing import (
    extract_questions_from_docx,
    extract_questions_from_xlsx,
)
from app.routers.matching import match_single_question

router = APIRouter(
    prefix="/companies/{company_id}/questionnaires", tags=["questionnaires"]
)

SUPPORTED_EXTENSIONS = {".xlsx", ".docx"}


@router.post("", response_model=QuestionnaireUploadResponse, status_code=201)
def upload_questionnaire(company_id: UUID, file: UploadFile = File(...)):
    filename = file.filename or ""
    _, ext = os.path.splitext(filename.lower())
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Supported: .xlsx, .docx",
        )

    # openpyxl/python-docx both want a real filesystem path, so spool
    # the upload to a temp file and pass its path in.
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        if ext == ".xlsx":
            questions = extract_questions_from_xlsx(tmp_path)
        else:
            questions = extract_questions_from_docx(tmp_path)
    finally:
        os.unlink(tmp_path)

    with get_db() as conn:
        row = conn.execute(
            """
            INSERT INTO questionnaires
                (company_id, original_filename, file_type, status)
            VALUES (%s, %s, %s, 'processing')
            RETURNING id
            """,
            (str(company_id), filename, ext.lstrip(".")),
        ).fetchone()
        questionnaire_id = row[0]

        counts = {"green": 0, "yellow": 0, "red": 0}
        for q in questions:
            match = match_single_question(company_id, q.question_text, conn)
            counts[match.confidence] += 1

            conn.execute(
                """
                INSERT INTO questionnaire_items
                    (questionnaire_id, row_number, question_text,
                     matched_answer_id, confidence_score, status,
                     final_answer_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(questionnaire_id),
                    q.row_number,
                    q.question_text,
                    str(match.id) if match.id is not None else None,
                    round(match.similarity, 3)
                    if match.similarity is not None
                    else None,
                    match.confidence,
                    match.answer_text,
                ),
            )

        conn.execute(
            "UPDATE questionnaires SET status = 'ready_for_review' WHERE id = %s",
            (str(questionnaire_id),),
        )

    return QuestionnaireUploadResponse(
        id=questionnaire_id,
        status="ready_for_review",
        total_questions=len(questions),
        green_count=counts["green"],
        yellow_count=counts["yellow"],
        red_count=counts["red"],
    )


@router.get(
    "/{questionnaire_id}/items", response_model=list[QuestionnaireItemOut]
)
def list_questionnaire_items(company_id: UUID, questionnaire_id: UUID):
    with get_db() as conn:
        # Verify the questionnaire actually belongs to this company before
        # returning its items — without this check, anyone could read any
        # questionnaire's items by guessing the id.
        exists = conn.execute(
            "SELECT 1 FROM questionnaires WHERE id = %s AND company_id = %s",
            (str(questionnaire_id), str(company_id)),
        ).fetchone()
        if exists is None:
            raise HTTPException(404, "Questionnaire not found")

        rows = conn.execute(
            """
            SELECT id, questionnaire_id, row_number, question_text,
                   matched_answer_id, confidence_score, status,
                   final_answer_text, approved, created_at
            FROM questionnaire_items
            WHERE questionnaire_id = %s
            ORDER BY row_number
            """,
            (str(questionnaire_id),),
        ).fetchall()

    return [_row_to_item(r) for r in rows]


@router.patch(
    "/{questionnaire_id}/items/{item_id}", response_model=QuestionnaireItemOut
)
def update_questionnaire_item(
    company_id: UUID,
    questionnaire_id: UUID,
    item_id: UUID,
    payload: QuestionnaireItemUpdate,
):
    fields, values = [], []
    if payload.final_answer_text is not None:
        fields.append("final_answer_text = %s")
        values.append(payload.final_answer_text)
    if payload.approved is not None:
        fields.append("approved = %s")
        values.append(payload.approved)
    if not fields:
        raise HTTPException(400, "No fields to update")

    with get_db() as conn:
        # Chain the full ownership check: item belongs to questionnaire
        # belongs to company. Without this, a caller could patch any item
        # by guessing its id regardless of which company/questionnaire the
        # URL claims it's under.
        exists = conn.execute(
            """
            SELECT 1
            FROM questionnaire_items qi
            JOIN questionnaires q ON q.id = qi.questionnaire_id
            WHERE qi.id = %s AND qi.questionnaire_id = %s AND q.company_id = %s
            """,
            (str(item_id), str(questionnaire_id), str(company_id)),
        ).fetchone()
        if exists is None:
            raise HTTPException(404, "Questionnaire item not found")

        values.append(str(item_id))
        row = conn.execute(
            f"""
            UPDATE questionnaire_items SET {", ".join(fields)}
            WHERE id = %s
            RETURNING id, questionnaire_id, row_number, question_text,
                      matched_answer_id, confidence_score, status,
                      final_answer_text, approved, created_at
            """,
            values,
        ).fetchone()

    return _row_to_item(row)


@router.post(
    "/{questionnaire_id}/rematch", response_model=QuestionnaireUploadResponse
)
def rematch_questionnaire(company_id: UUID, questionnaire_id: UUID):
    """
    Re-run matching for every item in an already-uploaded questionnaire.
    Lets a growing answer_bank fix items that were wrong at upload time
    without re-uploading the file. Approved items are left untouched —
    a human already signed off on those, so a fresh match shouldn't
    silently overwrite their decision.
    """
    with get_db() as conn:
        questionnaire_row = conn.execute(
            "SELECT status FROM questionnaires WHERE id = %s AND company_id = %s",
            (str(questionnaire_id), str(company_id)),
        ).fetchone()
        if questionnaire_row is None:
            raise HTTPException(404, "Questionnaire not found")
        questionnaire_status = questionnaire_row[0]

        items = conn.execute(
            """
            SELECT id, question_text, approved, status
            FROM questionnaire_items
            WHERE questionnaire_id = %s
            ORDER BY row_number
            """,
            (str(questionnaire_id),),
        ).fetchall()

        counts = {"green": 0, "yellow": 0, "red": 0}
        for item_id, question_text, is_approved, current_status in items:
            if is_approved:
                if current_status in counts:
                    counts[current_status] += 1
                continue

            match = match_single_question(company_id, question_text, conn)
            counts[match.confidence] += 1

            conn.execute(
                """
                UPDATE questionnaire_items
                SET matched_answer_id = %s,
                    confidence_score = %s,
                    status = %s,
                    final_answer_text = %s
                WHERE id = %s
                """,
                (
                    str(match.id) if match.id is not None else None,
                    round(match.similarity, 3)
                    if match.similarity is not None
                    else None,
                    match.confidence,
                    match.answer_text,
                    str(item_id),
                ),
            )

    return QuestionnaireUploadResponse(
        id=questionnaire_id,
        status=questionnaire_status,
        total_questions=len(items),
        green_count=counts["green"],
        yellow_count=counts["yellow"],
        red_count=counts["red"],
    )


def _row_to_item(row) -> QuestionnaireItemOut:
    return QuestionnaireItemOut(
        id=row[0],
        questionnaire_id=row[1],
        row_number=row[2],
        question_text=row[3],
        matched_answer_id=row[4],
        confidence_score=float(row[5]) if row[5] is not None else None,
        status=row[6],
        final_answer_text=row[7],
        approved=row[8],
        created_at=row[9],
    )
