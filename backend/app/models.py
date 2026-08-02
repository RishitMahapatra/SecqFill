from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AnswerCreate(BaseModel):
    question_text: str = Field(..., min_length=1, max_length=2000)
    answer_text: str = Field(..., min_length=1, max_length=5000)


class AnswerUpdate(BaseModel):
    question_text: Optional[str] = None
    answer_text: Optional[str] = None


class AnswerOut(BaseModel):
    id: UUID
    company_id: UUID
    question_text: str
    answer_text: str
    source: str
    times_used: int
    last_used_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class MatchRequest(BaseModel):
    question_text: str = Field(..., min_length=1, max_length=2000)


class MatchCandidate(BaseModel):
    id: UUID
    question_text: str
    answer_text: str
    similarity: float


class MatchResponse(BaseModel):
    # Nullable: there is no top match when the company's answer bank is
    # empty, but we still return a response (confidence "red") instead of
    # a 404 in that case.
    id: Optional[UUID]
    question_text: Optional[str]
    answer_text: Optional[str]
    similarity: Optional[float]
    confidence: Literal["green", "yellow", "red"]
    candidates: list[MatchCandidate]
