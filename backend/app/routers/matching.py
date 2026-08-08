"""
Matching endpoint — the core RAG lookup.

Given an incoming question, embed it and find the closest stored answers
via pgvector cosine distance, then bucket the result into a green/yellow/red
confidence level so the caller knows whether to trust the match, have a
human verify it, or skip straight to writing a fresh answer.
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter

from app.database import get_db
from app.embeddings import get_embedding
from app.models import MatchCandidate, MatchRequest, MatchResponse

router = APIRouter(prefix="/companies/{company_id}/match", tags=["matching"])

# Confidence bucketing thresholds — still estimates, not final, but now
# tuned against real observed data rather than a single example:
#
# MIN_SIMILARITY_THRESHOLD was 0.35, which real data showed doesn't separate
# "genuine match" from "no match at all" for nomic-embed-text: a nonsense,
# unrelated question ("What is your favorite pizza topping?") scored
# 0.367-0.369 across its top 3 candidates — all above 0.35, so it was never
# flagged red when it obviously should have been. Meanwhile, across a real
# 142-question test set against 32 answers spanning 13 security categories,
# the minimum score observed on a genuine match was 0.515. 0.42 sits between
# the pizza-question ceiling (~0.37) and the real-match floor (~0.515), but
# it's a starting estimate from two data points, not a final calibration —
# expect to retune as more real data comes in.
MIN_SIMILARITY_THRESHOLD = 0.42  # below this, treat as no usable match at all

# CONFIDENT_GAP_THRESHOLD used to be an absolute difference (0.08), which
# doesn't scale: as the answer bank grows with more topically-related
# answers, the gap between a still-correct top match and its (now also
# relevant) runner-up shrinks even though the top match hasn't gotten any
# less correct — so green counts could paradoxically drop as the bank got
# better. Using a relative gap (top - second) / top instead means the
# threshold scales proportionally as absolute scores shift, rather than
# needing a fixed subtraction to always mean the same thing. 0.15 is a
# starting estimate, not a final value.
CONFIDENT_RELATIVE_GAP_THRESHOLD = 0.15


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

    relative_gap = (top_similarity - candidates[1].similarity) / top_similarity
    if relative_gap < CONFIDENT_RELATIVE_GAP_THRESHOLD:
        return "yellow"

    return "green"


def match_single_question(
    company_id: UUID, question_text: str, conn
) -> MatchResponse:
    """
    Core "embed → search answer_bank → bucket confidence" for one question.
    Takes a live db connection so callers processing many questions in one
    request (e.g. a full questionnaire upload) can share one connection
    instead of opening/closing per question.
    """
    embedding = get_embedding(question_text)

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
        # Empty answer bank — no usable match, needs a human answer from
        # scratch. Report that as a red-confidence response rather than a
        # 404, since "no match yet" is an expected state, not an error.
        return MatchResponse(
            id=None,
            question_text=None,
            answer_text=None,
            similarity=None,
            confidence="red",
            candidates=[],
        )

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


@router.post("", response_model=MatchResponse)
def match_question(company_id: UUID, payload: MatchRequest):
    with get_db() as conn:
        return match_single_question(company_id, payload.question_text, conn)
