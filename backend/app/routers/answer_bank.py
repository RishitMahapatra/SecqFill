"""
Answer Bank CRUD.

Note: embeddings are intentionally left NULL here. Generating and storing
the vector embedding happens in Module 3 (matching pipeline) — keeping it
out of this module means we can build and test the CRUD layer without
needing an embedding model wired up yet.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException
from app.embeddings import get_embedding
from app.database import get_db
from app.models import AnswerCreate, AnswerOut, AnswerUpdate

router = APIRouter(prefix="/companies/{company_id}/answers", tags=["answer_bank"])


@router.post("", response_model=AnswerOut, status_code=201)
def create_answer(company_id: UUID, payload: AnswerCreate):
    # Embed the question text now, at write time — not later, on the fly,
    # during matching. This means matching a questionnaire against
    # thousands of stored answers is just a fast vector comparison,
    # not thousands of live embedding calls.
    embedding = get_embedding(payload.question_text)

    with get_db() as conn:
        row = conn.execute(
            """
            INSERT INTO answer_bank (company_id, question_text, answer_text, embedding)
            VALUES (%s, %s, %s, %s)
            RETURNING id, company_id, question_text, answer_text, source,
                      times_used, last_used_at, created_at, updated_at
            """,
            (str(company_id), payload.question_text, payload.answer_text, embedding),
        ).fetchone()
    return _row_to_answer(row)


@router.get("", response_model=list[AnswerOut])
def list_answers(company_id: UUID, limit: int = 100, offset: int = 0):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, company_id, question_text, answer_text, source,
                   times_used, last_used_at, created_at, updated_at
            FROM answer_bank
            WHERE company_id = %s
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
            """,
            (str(company_id), limit, offset),
        ).fetchall()
    return [_row_to_answer(r) for r in rows]


@router.patch("/{answer_id}", response_model=AnswerOut)
def update_answer(company_id: UUID, answer_id: UUID, payload: AnswerUpdate):
    fields, values = [], []
    if payload.question_text is not None:
        fields.append("question_text = %s")
        values.append(payload.question_text)
        # Question text changed — the old embedding no longer represents
        # this row, so we regenerate it now instead of leaving it stale/null.
        fields.append("embedding = %s")
        values.append(get_embedding(payload.question_text))
    if payload.answer_text is not None:
        fields.append("answer_text = %s")
        values.append(payload.answer_text)
    if not fields:
        raise HTTPException(400, "No fields to update")

    fields.append("updated_at = now()")
    values.extend([str(answer_id), str(company_id)])

    with get_db() as conn:
        row = conn.execute(
            f"""
            UPDATE answer_bank SET {", ".join(fields)}
            WHERE id = %s AND company_id = %s
            RETURNING id, company_id, question_text, answer_text, source,
                      times_used, last_used_at, created_at, updated_at
            """,
            values,
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Answer not found")
    return _row_to_answer(row)


@router.delete("/{answer_id}", status_code=204)
def delete_answer(company_id: UUID, answer_id: UUID):
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM answer_bank WHERE id = %s AND company_id = %s",
            (str(answer_id), str(company_id)),
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Answer not found")


def _row_to_answer(row) -> AnswerOut:
    return AnswerOut(
        id=row[0],
        company_id=row[1],
        question_text=row[2],
        answer_text=row[3],
        source=row[4],
        times_used=row[5],
        last_used_at=row[6],
        created_at=row[7],
        updated_at=row[8],
    )
