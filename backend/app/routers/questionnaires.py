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
from app.models import QuestionnaireItemOut, QuestionnaireUploadResponse
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
                   final_answer_text, created_at
            FROM questionnaire_items
            WHERE questionnaire_id = %s
            ORDER BY row_number
            """,
            (str(questionnaire_id),),
        ).fetchall()

    return [
        QuestionnaireItemOut(
            id=r[0],
            questionnaire_id=r[1],
            row_number=r[2],
            question_text=r[3],
            matched_answer_id=r[4],
            confidence_score=float(r[5]) if r[5] is not None else None,
            status=r[6],
            final_answer_text=r[7],
            created_at=r[8],
        )
        for r in rows
    ]
