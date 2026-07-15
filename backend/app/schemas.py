from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class KnowledgePointOut(ORMModel):
    id: int
    name: str
    position: int
    status: str
    mastery: float


class ChapterOut(ORMModel):
    id: int
    name: str
    position: int
    points: list[KnowledgePointOut]


class SubjectOut(ORMModel):
    id: int
    name: str
    position: int
    chapters: list[ChapterOut]


class ExamOut(ORMModel):
    id: int
    name: str
    code: str
    subjects: list[SubjectOut]


class TreeNodeCreate(BaseModel):
    parent_id: int
    name: str = Field(min_length=1, max_length=180)


class TreeNodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    position: int | None = None
    archived: bool | None = None
    status: str | None = None


class DocumentOut(ORMModel):
    id: int
    name: str
    original_name: str
    mime_type: str
    status: str
    parse_status: str
    outline_status: str
    error: str | None
    exam_id: int | None
    subject_id: int | None
    chapter_id: int | None
    created_at: datetime
    job_id: int | None = None


class DocumentUpdate(BaseModel):
    name: str | None = None
    exam_id: int | None = None
    subject_id: int | None = None
    chapter_id: int | None = None


class CitationOut(BaseModel):
    chunk_id: int
    document_id: int
    document_name: str
    locator: str
    quote: str


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    conversation_id: int | None = None
    subject_id: int | None = None
    chapter_id: int | None = None
    mode: str = "answer"
    page_context: dict[str, Any] = Field(default_factory=dict)


class AskResponse(BaseModel):
    conversation_id: int
    answer: str
    citations: list[CitationOut]
    reasoning_type: str
    grounded: bool
    insufficient_evidence: list[str]
    suggested_materials: list[str]
    follow_up_questions: list[str]
    conversation_summary: str = ""


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    content: str = ""
    tags: list[str] = []
    favorite: bool = False
    subject_id: int | None = None
    chapter_id: int | None = None
    knowledge_point_id: int | None = None
    source_type: str | None = None
    source_id: int | None = None


class NoteOut(ORMModel):
    id: int
    title: str
    content: str
    tags: list[str]
    favorite: bool
    subject_id: int | None
    chapter_id: int | None
    knowledge_point_id: int | None
    source_type: str | None
    source_id: int | None
    updated_at: datetime


class ReviewOut(ORMModel):
    id: int
    knowledge_point_id: int
    prompt: str
    answer: str
    citations: list
    due_date: date
    interval_days: int
    attempts: int


class ReviewResult(BaseModel):
    quality: int = Field(ge=0, le=5)


class AssessmentCreate(BaseModel):
    subject_id: int
    chapter_id: int | None = None
    assessment_type: str = "diagnostic"
    question_count: int = Field(default=5, ge=1, le=20)


class AttemptIn(BaseModel):
    question_id: int
    response: str
    self_rating: int = Field(default=3, ge=1, le=5)
    duration_seconds: int = Field(default=0, ge=0, le=86400)


class AISettingIn(BaseModel):
    api_key: str = Field(min_length=8)
    model: str = "deepseek-chat"


class AISettingOut(BaseModel):
    configured: bool
    model: str
    verified: bool


class SessionIn(BaseModel):
    subject_id: int | None = None
    chapter_id: int | None = None
    knowledge_point_id: int | None = None
    route: str = "dashboard"
    context: dict = {}


class ProposalNodeUpdate(BaseModel):
    id: int | None = None
    node_type: str = Field(pattern="^(chapter|point)$")
    title: str = Field(min_length=1, max_length=180)
    position: int
    parent_id: int | None = None
    action: str = Field(pattern="^(create|merge|ignore)$")
    target_node_id: int | None = None
    source_chunk_ids: list[int] = []
    source_locators: list[str] = []


class ProposalUpdate(BaseModel):
    nodes: list[ProposalNodeUpdate]
