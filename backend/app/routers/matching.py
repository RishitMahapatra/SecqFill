"""
Matching endpoint — the core RAG lookup.

Given an incoming question, embed it and find the closest stored answers
via pgvector cosine distance, then bucket the result into a green/yellow/red
confidence level so the caller knows whether to trust the match, have a
human verify it, or skip straight to writing a fresh answer.
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.embeddings import get_embedding
from app.models import MatchCandidate, MatchRequest, MatchResponse

router = APIRouter(prefix="/companies/{company_id}/match", tags=["matching"])

# Confidence bucketing thresholds — initial estimates, not final. Based on one
# real example (nomic-embed-text), a correct match scored 0.541 while the
# runner-up scored 0.380: absolute similarity for this model sits lower than
# intuition suggests, so a fixed "0.8 = confident" cutoff would be wrong.
# Expect to retune both constants once we've tested against more real data.
MIN_SIMILARITY_THRESHOLD = 0.35  # below this, treat as no usable match at all
CONFIDENT_GAP_THRESHOLD = 0.08   # gap over the runner-up needed to call it "green"


def _bucket_confidence(candidates: list[MatchCandidate]) -> Literal["green", "yellow", "red"]:
    if not candidates:
        return "red"

    top_similarity = candidates[0].similarity
    if top_similarity < MIN_SIMILARITY_THRESHOLD:
        return "red"

    if len(candidates) < 2:
        # No runner-up to measure a gap against — fall back to the absolute
        # threshold alone, which we already know is satisfied above.
        return "green"

    gap = top_similarity - candidates[1].similarity
    if gap < CONFIDENT_GAP_THRESHOLD:
        return "yellow"

    return "green"


@router.post("", response_model=MatchResponse)
def match_question(company_id: UUID, payload: MatchRequest):
    embedding = get_embedding(payload.question_text)

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, question_text, answer_text, embedding <=> %s::vector AS distance
            FROM answer_bank
            WHERE company_id = %s
            ORDER BY embedding <=> %s::vector
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
        confidence=_bucket_confidence(candidates),
        candidates=candidates,
    )
