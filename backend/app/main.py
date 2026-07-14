import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, or_, select, text
from sqlalchemy.orm import Session, selectinload

from .ai import grounded_answer
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .documents import parse_document
from .learning import embed, schedule_review
from .models import (
    AIProviderSetting, Chapter, Conversation, CurriculumProposal, CurriculumSourceLink,
    Document, DocumentChunk, ExamTrack, KnowledgePoint, Message, Note, ProposalNode,
    ReviewItem, StudySession, Subject,
)
from .schemas import (
    AISettingIn, AISettingOut, AskRequest, AskResponse, DocumentOut, DocumentUpdate,
    ExamOut, NoteCreate, NoteOut, ProposalUpdate, ReviewOut, ReviewResult,
    SessionIn, TreeNodeCreate, TreeNodeUpdate,
)
from .outlines import process_outline


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_application()
    yield


app = FastAPI(title="砚台 · 财务学习 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in settings.cors_origins.split(",")],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


CURRICULA = {
    "CPA": ["会计", "审计", "财务成本管理", "经济法", "税法", "公司战略与风险管理"],
    "税务师": ["税法（一）", "税法（二）", "涉税服务实务", "涉税服务相关法律", "财务与会计"],
}


def seed_curricula(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(ExamTrack)):
        return
    for code, subjects in CURRICULA.items():
        exam = ExamTrack(name="注册会计师" if code == "CPA" else "税务师职业资格", code=code)
        db.add(exam)
        db.flush()
        for index, subject_name in enumerate(subjects):
            subject = Subject(exam_id=exam.id, name=subject_name, position=index)
            db.add(subject)
            db.flush()
            chapter = Chapter(subject_id=subject.id, name="未编排章节", position=0)
            db.add(chapter)
            db.flush()
            db.add(KnowledgePoint(chapter_id=chapter.id, name="上传资料后编辑知识点", position=0))
    db.commit()


def migrate_additive_schema() -> None:
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("documents")}
        if "parse_status" not in columns:
            connection.execute(text("ALTER TABLE documents ADD COLUMN parse_status VARCHAR(30) DEFAULT 'processing'"))
            connection.execute(text("UPDATE documents SET parse_status = CASE WHEN status = 'ready' THEN 'ready' ELSE status END"))
        if "outline_status" not in columns:
            connection.execute(text("ALTER TABLE documents ADD COLUMN outline_status VARCHAR(30) DEFAULT 'waiting'"))


def initialize_application() -> None:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    migrate_additive_schema()
    with SessionLocal() as db:
        seed_curricula(db)
        interrupted = db.scalars(select(CurriculumProposal).where(CurriculumProposal.status.in_(["extracting", "enhancing"]))).all()
        for proposal in interrupted:
            proposal.status = "failed"
            proposal.error = "服务重启导致任务中断，请点击重试。"
            document = db.get(Document, proposal.document_id)
            if document:
                document.outline_status = "failed"
        db.commit()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ledger-study"}


@app.get("/api/curriculum", response_model=list[ExamOut])
def curriculum(db: Session = Depends(get_db)):
    stmt = select(ExamTrack).options(
        selectinload(ExamTrack.subjects).selectinload(Subject.chapters).selectinload(Chapter.points)
    ).order_by(ExamTrack.id)
    exams = db.scalars(stmt).unique().all()
    for exam in exams:
        exam.subjects.sort(key=lambda x: x.position)
        for subject in exam.subjects:
            subject.chapters.sort(key=lambda x: x.position)
            for chapter in subject.chapters:
                chapter.points.sort(key=lambda x: x.position)
    return exams


@app.post("/api/curriculum/chapters")
def create_chapter(body: TreeNodeCreate, db: Session = Depends(get_db)):
    if not db.get(Subject, body.parent_id):
        raise HTTPException(404, "科目不存在")
    position = db.scalar(select(func.count()).select_from(Chapter).where(Chapter.subject_id == body.parent_id)) or 0
    row = Chapter(subject_id=body.parent_id, name=body.name, position=position)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name}


@app.post("/api/curriculum/points")
def create_point(body: TreeNodeCreate, db: Session = Depends(get_db)):
    if not db.get(Chapter, body.parent_id):
        raise HTTPException(404, "章节不存在")
    position = db.scalar(select(func.count()).select_from(KnowledgePoint).where(KnowledgePoint.chapter_id == body.parent_id)) or 0
    row = KnowledgePoint(chapter_id=body.parent_id, name=body.name, position=position)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name}


@app.patch("/api/curriculum/{kind}/{node_id}")
def update_node(kind: str, node_id: int, body: TreeNodeUpdate, db: Session = Depends(get_db)):
    model = {"subjects": Subject, "chapters": Chapter, "points": KnowledgePoint}.get(kind)
    if not model:
        raise HTTPException(400, "未知节点类型")
    row = db.get(model, node_id)
    if not row:
        raise HTTPException(404, "节点不存在")
    for key, value in body.model_dump(exclude_none=True).items():
        if hasattr(row, key): setattr(row, key, value)
    db.commit()
    return {"ok": True}


@app.get("/api/documents", response_model=list[DocumentOut])
def documents(db: Session = Depends(get_db)):
    return db.scalars(select(Document).order_by(Document.created_at.desc())).all()


@app.post("/api/documents", response_model=DocumentOut)
def upload_document(
    background_tasks: BackgroundTasks, file: UploadFile = File(...), exam_id: int | None = Form(None),
    subject_id: int = Form(...), chapter_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md", ".markdown"}:
        raise HTTPException(400, "仅支持 PDF、DOCX、TXT 和 Markdown")
    target = settings.storage_dir / f"{uuid.uuid4().hex}{suffix}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    subject = db.get(Subject, subject_id)
    if not subject:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "上传资料必须选择有效科目")
    row = Document(name=Path(file.filename or "资料").stem, original_name=file.filename or "资料",
                   path=str(target), mime_type=file.content_type or "application/octet-stream",
                   exam_id=exam_id or subject.exam_id, subject_id=subject_id, chapter_id=chapter_id,
                   parse_status="processing", outline_status="waiting")
    db.add(row); db.commit(); db.refresh(row)
    try:
        parsed = parse_document(target, suffix)
        for index, chunk in enumerate(parsed):
            db.add(DocumentChunk(document_id=row.id, position=index, embedding=embed(chunk["content"]), **chunk))
        row.status = "ready"; row.parse_status = "ready"; row.outline_status = "extracting"
        db.commit(); db.refresh(row)
        proposal = CurriculumProposal(document_id=row.id, subject_id=subject_id, status="extracting")
        db.add(proposal); db.commit(); db.refresh(proposal)
        background_tasks.add_task(process_outline, proposal.id)
    except Exception as exc:
        row.status = "failed"; row.parse_status = "failed"; row.outline_status = "failed"; row.error = str(exc)[:500]
    db.commit(); db.refresh(row)
    return row


@app.get("/api/documents/{document_id}/chunks")
def document_chunks(document_id: int, locator: str | None = None, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "资料不存在")
    stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.position)
    if locator: stmt = stmt.where(DocumentChunk.locator == locator)
    chunks = db.scalars(stmt).all()
    return {"document": {"id": document.id, "name": document.name, "status": document.status},
            "chunks": [{"id": c.id, "content": c.content, "locator": c.locator, "heading": c.heading} for c in chunks]}


@app.patch("/api/documents/{document_id}", response_model=DocumentOut)
def update_document(document_id: int, body: DocumentUpdate, db: Session = Depends(get_db)):
    row = db.get(Document, document_id)
    if not row: raise HTTPException(404, "资料不存在")
    for key, value in body.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    db.commit(); db.refresh(row); return row


@app.post("/api/documents/{document_id}/reindex", response_model=DocumentOut)
def reindex_document(document_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    row = db.get(Document, document_id)
    if not row: raise HTTPException(404, "资料不存在")
    db.query(CurriculumSourceLink).filter(CurriculumSourceLink.document_id == row.id).delete(synchronize_session=False)
    db.query(DocumentChunk).filter(DocumentChunk.document_id == row.id).delete()
    row.status = "processing"; row.parse_status = "processing"; row.outline_status = "waiting"; row.error = None; db.commit()
    try:
        parsed = parse_document(Path(row.path), Path(row.path).suffix)
        for index, chunk in enumerate(parsed):
            db.add(DocumentChunk(document_id=row.id, position=index, embedding=embed(chunk["content"]), **chunk))
        row.status = "ready"; row.parse_status = "ready"; row.outline_status = "extracting"
        db.commit(); db.refresh(row)
        if row.subject_id:
            proposal = CurriculumProposal(document_id=row.id, subject_id=row.subject_id, status="extracting")
            db.add(proposal); db.commit(); db.refresh(proposal)
            background_tasks.add_task(process_outline, proposal.id)
    except Exception as exc:
        row.status = "failed"; row.parse_status = "failed"; row.outline_status = "failed"; row.error = str(exc)[:500]
    db.commit(); db.refresh(row); return row


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: int, confirm: bool = Query(False), db: Session = Depends(get_db)):
    if not confirm: raise HTTPException(400, "删除资料必须明确确认")
    row = db.get(Document, document_id)
    if not row: raise HTTPException(404, "资料不存在")
    path = Path(row.path)
    db.query(CurriculumSourceLink).filter(CurriculumSourceLink.document_id == row.id).delete(synchronize_session=False)
    db.delete(row); db.commit()
    path.unlink(missing_ok=True)
    return {"ok": True, "historical_citations": "preserved_as_unavailable"}


def proposal_payload(db: Session, proposal: CurriculumProposal) -> dict:
    nodes = db.scalars(select(ProposalNode).where(ProposalNode.proposal_id == proposal.id).order_by(ProposalNode.node_type, ProposalNode.position)).all()
    chapter_nodes = [node for node in nodes if node.node_type == "chapter"]
    point_nodes = [node for node in nodes if node.node_type == "point"]
    return {
        "id": proposal.id, "document_id": proposal.document_id, "subject_id": proposal.subject_id,
        "status": proposal.status, "ai_enhanced": proposal.ai_enhanced, "model": proposal.model,
        "error": proposal.error, "warning": proposal.warning, "result_summary": proposal.result_summary,
        "created_at": proposal.created_at, "updated_at": proposal.updated_at,
        "nodes": [{
            "id": chapter.id, "node_type": "chapter", "title": chapter.title, "original_title": chapter.original_title,
            "position": chapter.position, "confidence": chapter.confidence, "source_chunk_ids": chapter.source_chunk_ids,
            "source_locators": chapter.source_locators, "action": chapter.action, "target_node_id": chapter.target_node_id,
            "children": [{
                "id": point.id, "node_type": "point", "title": point.title, "original_title": point.original_title,
                "position": point.position, "confidence": point.confidence, "source_chunk_ids": point.source_chunk_ids,
                "source_locators": point.source_locators, "action": point.action, "target_node_id": point.target_node_id,
            } for point in sorted((item for item in point_nodes if item.parent_id == chapter.id), key=lambda x: x.position)],
        } for chapter in sorted(chapter_nodes, key=lambda x: x.position)],
    }


@app.get("/api/documents/{document_id}/outline")
def get_document_outline(document_id: int, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "资料不存在")
    proposal = db.scalar(select(CurriculumProposal).where(CurriculumProposal.document_id == document_id).order_by(CurriculumProposal.id.desc()))
    if not proposal:
        return {"document_id": document_id, "status": document.outline_status, "nodes": []}
    return proposal_payload(db, proposal)


@app.post("/api/documents/{document_id}/outline")
def generate_document_outline(document_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "资料不存在")
    if document.parse_status != "ready" or not document.subject_id:
        raise HTTPException(409, "资料尚未解析完成或没有绑定科目")
    proposal = CurriculumProposal(document_id=document.id, subject_id=document.subject_id, status="extracting")
    document.outline_status = "extracting"
    db.add(proposal); db.commit(); db.refresh(proposal)
    background_tasks.add_task(process_outline, proposal.id)
    return proposal_payload(db, proposal)


@app.patch("/api/outline-proposals/{proposal_id}")
def update_outline_proposal(proposal_id: int, body: ProposalUpdate, db: Session = Depends(get_db)):
    proposal = db.get(CurriculumProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "目录草稿不存在")
    if proposal.status != "review":
        raise HTTPException(409, "只有待确认草稿可以编辑")
    owned = {node.id: node for node in db.scalars(select(ProposalNode).where(ProposalNode.proposal_id == proposal_id)).all()}
    for patch in body.nodes:
        node = owned.get(patch.id) if patch.id else None
        if patch.id and not node:
            raise HTTPException(400, f"节点 {patch.id} 不属于当前草稿")
        if patch.parent_id is not None and patch.parent_id not in owned:
            raise HTTPException(400, "父节点不属于当前草稿")
        if not node:
            node = ProposalNode(
                proposal_id=proposal.id, node_type=patch.node_type, title=patch.title, original_title=patch.title,
                confidence=0.5, source_chunk_ids=patch.source_chunk_ids, source_locators=patch.source_locators,
            )
            db.add(node)
        node.title = patch.title; node.position = patch.position; node.parent_id = patch.parent_id
        node.action = patch.action; node.target_node_id = patch.target_node_id
    db.commit(); db.refresh(proposal)
    return proposal_payload(db, proposal)


def add_source_links(db: Session, document_id: int, chunk_ids: list[int], chapter_id: int | None, point_id: int | None) -> None:
    for chunk_id in set(chunk_ids):
        exists = db.scalar(select(CurriculumSourceLink).where(
            CurriculumSourceLink.document_id == document_id, CurriculumSourceLink.chunk_id == chunk_id,
            CurriculumSourceLink.chapter_id == chapter_id, CurriculumSourceLink.knowledge_point_id == point_id,
        ))
        if not exists:
            db.add(CurriculumSourceLink(document_id=document_id, chunk_id=chunk_id, chapter_id=chapter_id, knowledge_point_id=point_id))


@app.post("/api/outline-proposals/{proposal_id}/confirm")
def confirm_outline_proposal(proposal_id: int, db: Session = Depends(get_db)):
    proposal = db.get(CurriculumProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "目录草稿不存在")
    if proposal.status == "confirmed":
        return {"ok": True, "idempotent": True, **proposal.result_summary}
    if proposal.status != "review":
        raise HTTPException(409, "草稿尚未达到可确认状态")
    nodes = db.scalars(select(ProposalNode).where(ProposalNode.proposal_id == proposal.id)).all()
    chapters = sorted((node for node in nodes if node.node_type == "chapter"), key=lambda x: x.position)
    actual_chapters: dict[int, int] = {}
    created_chapters = created_points = merged = 0
    try:
        for node in chapters:
            if node.action == "ignore":
                continue
            chapter = db.get(Chapter, node.target_node_id) if node.action == "merge" and node.target_node_id else None
            if chapter and chapter.subject_id != proposal.subject_id:
                raise HTTPException(400, "合并目标不属于当前科目")
            if not chapter:
                chapter = Chapter(subject_id=proposal.subject_id, name=node.title, position=node.position)
                db.add(chapter); db.flush(); created_chapters += 1
            else:
                merged += 1
            actual_chapters[node.id] = chapter.id
            add_source_links(db, proposal.document_id, node.source_chunk_ids, chapter.id, None)
        for node in sorted((item for item in nodes if item.node_type == "point"), key=lambda x: x.position):
            if node.action == "ignore" or node.parent_id not in actual_chapters:
                continue
            chapter_id = actual_chapters[node.parent_id]
            point = db.get(KnowledgePoint, node.target_node_id) if node.action == "merge" and node.target_node_id else None
            if point and point.chapter_id != chapter_id:
                point = None
            if not point:
                point = KnowledgePoint(chapter_id=chapter_id, name=node.title, position=node.position)
                db.add(point); db.flush(); created_points += 1
            else:
                merged += 1
            add_source_links(db, proposal.document_id, node.source_chunk_ids, chapter_id, point.id)
        proposal.status = "confirmed"
        proposal.result_summary = {**proposal.result_summary, "created_chapters": created_chapters, "created_points": created_points, "merged": merged}
        document = db.get(Document, proposal.document_id)
        if document: document.outline_status = "confirmed"
        db.commit()
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback(); raise HTTPException(500, f"确认目录失败：{exc}") from exc
    return {"ok": True, "idempotent": False, **proposal.result_summary}


@app.post("/api/outline-proposals/{proposal_id}/retry")
def retry_outline_proposal(proposal_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    proposal = db.get(CurriculumProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "目录草稿不存在")
    if proposal.status == "confirmed":
        raise HTTPException(409, "已确认草稿不能重试")
    db.query(ProposalNode).filter(ProposalNode.proposal_id == proposal.id).delete()
    proposal.status = "extracting"; proposal.error = None; proposal.warning = None
    document = db.get(Document, proposal.document_id)
    if document: document.outline_status = "extracting"
    db.commit(); background_tasks.add_task(process_outline, proposal.id)
    return {"ok": True, "status": "extracting"}


@app.delete("/api/outline-proposals/{proposal_id}")
def discard_outline_proposal(proposal_id: int, db: Session = Depends(get_db)):
    proposal = db.get(CurriculumProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "目录草稿不存在")
    if proposal.status == "confirmed":
        raise HTTPException(409, "已确认草稿不能删除")
    document = db.get(Document, proposal.document_id)
    db.delete(proposal)
    if document: document.outline_status = "waiting"
    db.commit(); return {"ok": True}


@app.post("/api/ai/ask", response_model=AskResponse)
def ask(body: AskRequest, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, body.conversation_id) if body.conversation_id else None
    if not conversation:
        conversation = Conversation(title=body.question[:50], mode=body.mode, subject_id=body.subject_id, chapter_id=body.chapter_id)
        db.add(conversation); db.flush()
    db.add(Message(conversation_id=conversation.id, role="user", content=body.question))
    try:
        answer = grounded_answer(db, body.question, body.subject_id, body.chapter_id, body.mode)
    except httpx.HTTPStatusError as exc:
        db.rollback(); raise HTTPException(502, f"DeepSeek 请求失败：HTTP {exc.response.status_code}")
    except (httpx.HTTPError, ValueError) as exc:
        db.rollback(); raise HTTPException(422, str(exc))
    db.add(Message(conversation_id=conversation.id, role="assistant", content=answer["answer"], payload=answer))
    conversation.updated_at = datetime.utcnow(); db.commit()
    return {"conversation_id": conversation.id, **answer}


@app.get("/api/conversations")
def conversations(db: Session = Depends(get_db)):
    rows = db.scalars(select(Conversation).order_by(Conversation.updated_at.desc())).all()
    return [{"id": x.id, "title": x.title, "mode": x.mode, "subject_id": x.subject_id,
             "chapter_id": x.chapter_id, "updated_at": x.updated_at} for x in rows]


@app.get("/api/conversations/{conversation_id}")
def conversation(conversation_id: int, db: Session = Depends(get_db)):
    row = db.get(Conversation, conversation_id)
    if not row: raise HTTPException(404, "会话不存在")
    messages = db.scalars(select(Message).where(Message.conversation_id == row.id).order_by(Message.id)).all()
    return {"id": row.id, "title": row.title, "mode": row.mode,
            "messages": [{"id": m.id, "role": m.role, "content": m.content, "payload": m.payload} for m in messages]}


@app.get("/api/notes", response_model=list[NoteOut])
def notes(search: str = "", db: Session = Depends(get_db)):
    stmt = select(Note).order_by(Note.updated_at.desc())
    if search: stmt = stmt.where(or_(Note.title.contains(search), Note.content.contains(search)))
    return db.scalars(stmt).all()


@app.post("/api/notes", response_model=NoteOut)
def create_note(body: NoteCreate, db: Session = Depends(get_db)):
    row = Note(**body.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@app.put("/api/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, body: NoteCreate, db: Session = Depends(get_db)):
    row = db.get(Note, note_id)
    if not row: raise HTTPException(404, "笔记不存在")
    for key, value in body.model_dump().items(): setattr(row, key, value)
    db.commit(); db.refresh(row); return row


@app.get("/api/reviews/today", response_model=list[ReviewOut])
def reviews_today(db: Session = Depends(get_db)):
    return db.scalars(select(ReviewItem).where(ReviewItem.due_date <= date.today()).order_by(ReviewItem.due_date)).all()


@app.post("/api/reviews/from-point/{point_id}", response_model=ReviewOut)
def create_review(point_id: int, db: Session = Depends(get_db)):
    point = db.get(KnowledgePoint, point_id)
    if not point: raise HTTPException(404, "知识点不存在")
    existing = db.scalar(select(ReviewItem).where(ReviewItem.knowledge_point_id == point_id))
    if existing: return existing
    row = ReviewItem(knowledge_point_id=point.id, prompt=f"请用自己的话解释：{point.name}",
                     answer="请结合已上传资料核对你的解释。", due_date=date.today())
    db.add(row); db.commit(); db.refresh(row); return row


@app.post("/api/reviews/{review_id}/complete", response_model=ReviewOut)
def complete_review(review_id: int, body: ReviewResult, db: Session = Depends(get_db)):
    row = db.get(ReviewItem, review_id)
    if not row: raise HTTPException(404, "复习任务不存在")
    return schedule_review(db, row, body.quality)


@app.get("/api/settings/ai", response_model=AISettingOut)
def get_ai_setting(db: Session = Depends(get_db)):
    row = db.get(AIProviderSetting, 1)
    return {"configured": bool(row and row.encrypted_key), "model": row.model if row else "deepseek-chat", "verified": bool(row and row.verified)}


@app.put("/api/settings/ai", response_model=AISettingOut)
def save_ai_setting(body: AISettingIn, db: Session = Depends(get_db)):
    row = db.get(AIProviderSetting, 1) or AIProviderSetting(id=1)
    row.encrypted_key = settings.fernet().encrypt(body.api_key.encode()).decode()
    row.model = body.model; row.verified = False
    db.add(row); db.commit()
    return {"configured": True, "model": row.model, "verified": False}


@app.post("/api/settings/ai/test", response_model=AISettingOut)
def test_ai_setting(db: Session = Depends(get_db)):
    row = db.get(AIProviderSetting, 1)
    if not row or not row.encrypted_key: raise HTTPException(400, "尚未配置 API Key")
    key = settings.fernet().decrypt(row.encrypted_key.encode()).decode()
    try:
        response = httpx.get(f"{settings.deepseek_base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"}, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "DeepSeek Key 验证失败") from exc
    row.verified = True; db.commit()
    return {"configured": True, "model": row.model, "verified": True}


@app.delete("/api/settings/ai")
def clear_ai_setting(db: Session = Depends(get_db)):
    row = db.get(AIProviderSetting, 1)
    if row: db.delete(row); db.commit()
    return {"ok": True}


@app.post("/api/sessions")
def save_session(body: SessionIn, db: Session = Depends(get_db)):
    row = StudySession(**body.model_dump()); db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "studied_at": row.studied_at}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    points = db.scalars(select(KnowledgePoint)).all()
    reviews = db.scalar(select(func.count()).select_from(ReviewItem).where(ReviewItem.due_date <= date.today())) or 0
    documents = db.scalar(select(func.count()).select_from(Document).where(Document.status == "ready")) or 0
    notes_count = db.scalar(select(func.count()).select_from(Note)) or 0
    recent = db.scalar(select(StudySession).order_by(StudySession.studied_at.desc()))
    active_days = {x.date() for x in db.scalars(select(StudySession.studied_at).where(StudySession.studied_at >= datetime.utcnow() - timedelta(days=30))).all()}
    streak = 0; cursor = date.today()
    while cursor in active_days: streak += 1; cursor -= timedelta(days=1)
    weak = sorted(points, key=lambda x: x.mastery)[:5]
    return {"review_due": reviews, "documents": documents, "notes": notes_count, "streak": streak,
            "progress": round(sum(p.mastery for p in points) / max(1, len(points))),
            "weak_points": [{"id": p.id, "name": p.name, "mastery": p.mastery} for p in weak],
            "recent_session": {"route": recent.route, "context": recent.context} if recent else None}
