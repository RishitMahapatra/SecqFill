"""
Matching endpoint — the core RAG lookup.

Given an incoming question, embed it and find the closest stored answers
via pgvector cosine distance. No LLM call and no confidence bucketing here
yet; this module's only job is proving vector similarity search finds the
right stored answer.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.embeddings import get_embedding
from app.models import MatchCandidate, MatchRequest, MatchResponse

router = APIRouter(prefix="/companies/{company_id}/match", tags=["matching"])


@router.post("", response_model=MatchResponse)
def match_question(company_id: UUID, payload: MatchRequest):
    embedding = get_embedding(payload.question_text)

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, question_text, answer_text, embedding <=> %s AS distance
            FROM answer_bank
            WHERE company_id = %s
            ORDER BY embedding <=> %s
            LIMIT 3
            """,
            (embedding, str(company_id), embedding),
        ).fetchall()

    if not rows:
        raise HTTPException(404, "No answers found for this company")

    candidates = [
        MatchCandidate(
            id=row[0],
            question_text=row[1],
            answer_text=row[2],
            similarity=1 - row[3],
        )
        for row in rows
    ]

    top = candidates[0]
    return MatchResponse(
        id=top.id,
        question_text=top.question_text,
        answer_text=top.answer_text,
        similarity=top.similarity,
        candidates=candidates,
    )
