import json
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .learning import cosine, embed, tokenize
from .models import AIProviderSetting, CurriculumSourceLink, Document, DocumentChunk


def retrieve(db: Session, question: str, subject_id: int | None, chapter_id: int | None, limit: int = 6):
    stmt = select(DocumentChunk, Document).join(Document, DocumentChunk.document_id == Document.id).where(Document.status == "ready")
    if subject_id:
        stmt = stmt.where(Document.subject_id == subject_id)
    if chapter_id:
        linked_chunks = select(CurriculumSourceLink.chunk_id).where(CurriculumSourceLink.chapter_id == chapter_id)
        stmt = stmt.where((Document.chapter_id == chapter_id) | (DocumentChunk.id.in_(linked_chunks)))
    query_tokens = set(tokenize(question))
    ranked = []
    if db.bind and db.bind.dialect.name == "postgresql":
        from .embeddings import semantic_embed
        query_vec = semantic_embed(question)
        distance = DocumentChunk.vector.cosine_distance(query_vec).label("distance")
        rows = db.execute(stmt.add_columns(distance).where(DocumentChunk.vector.is_not(None)).order_by(distance).limit(30)).all()
        for chunk, document, vector_distance in rows:
            lexical = len(query_tokens.intersection(tokenize(chunk.content))) / max(1, len(query_tokens))
            score = (1 - float(vector_distance)) * 0.72 + lexical * 0.28
            ranked.append((score, chunk, document))
    else:
        query_vec = embed(question)
        rows = db.execute(stmt.limit(2000)).all()
        for chunk, document in rows:
            lexical = len(query_tokens.intersection(tokenize(chunk.content))) / max(1, len(query_tokens))
            score = cosine(query_vec, chunk.embedding) * 0.65 + lexical * 0.35
            ranked.append((score, chunk, document))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item for item in ranked[:limit] if item[0] >= 0.08]


def decrypt_key(db: Session) -> tuple[str, str]:
    row = db.get(AIProviderSetting, 1)
    if not row or not row.encrypted_key:
        raise ValueError("请先在设置中配置 DeepSeek API Key")
    key, migrated = settings.decrypt_secret(row.encrypted_key)
    if migrated:
        row.encrypted_key = migrated
        db.commit()
    return key, row.model


def _expanded_chunk_context(db: Session, chunk: DocumentChunk) -> str:
    """把命中片段的前后相邻段落带进工作上下文，引用仍归属于命中片段。"""
    document_id = getattr(chunk, "document_id", None)
    position = getattr(chunk, "position", None)
    if document_id is None or position is None or not hasattr(db, "scalars"):
        return chunk.content
    rows = db.scalars(
        select(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.position >= max(0, position - 1),
            DocumentChunk.position <= position + 1,
        ).order_by(DocumentChunk.position)
    ).all()
    return "\n".join(f"{row.locator}：{row.content}" for row in rows)


def grounded_answer(
    db: Session,
    question: str,
    subject_id: int | None,
    chapter_id: int | None,
    mode: str,
    history: list[dict[str, str]] | None = None,
    page_context: dict[str, Any] | None = None,
    conversation_summary: str = "",
) -> dict[str, Any]:
    evidence = retrieve(db, question, subject_id, chapter_id)
    citations = [
        {"chunk_id": chunk.id, "document_id": doc.id, "document_name": doc.name,
         "locator": chunk.locator, "quote": chunk.content}
        for _, chunk, doc in evidence
    ]
    if not citations:
        return {
            "answer": "当前资料不足以回答这个问题。请上传或绑定包含相关知识点的教材、讲义或法规资料。",
            "citations": [], "reasoning_type": "insufficient", "grounded": False,
            "insufficient_evidence": ["没有检索到与问题直接相关的资料片段"],
            "suggested_materials": ["相关科目的教材章节", "适用的法规或考试讲义"],
            "follow_up_questions": [],
            "conversation_summary": conversation_summary,
        }
    api_key, model = decrypt_key(db)
    evidence_text = "\n\n".join(
        f"[C{item['chunk_id']}] {item['document_name']} {item['locator']}\n"
        f"{_expanded_chunk_context(db, chunk)}"
        for item, (_, chunk, _) in zip(citations, evidence)
    )
    mode_instruction = "使用苏格拉底式追问，不直接给最终结论。" if mode == "socratic" else "直接、分层地回答。"
    page_context_text = json.dumps(page_context or {}, ensure_ascii=False)
    system = f"""你是严谨的财务考证助教。你只能使用下方证据，不得使用常识补充。{mode_instruction}
    历史对话只用于理解当前问题的指代和上下文，不是事实来源；历史内容与下方证据冲突时，以证据为准。
    当前网页上下文只用于理解用户正在学习的位置，不是事实来源。
    请在 conversation_summary 中用不超过 500 字总结：用户已经理解什么、仍然困惑什么、下一步适合做什么。
    把回答拆成 claims；每个 claim 必须包含 text、citation_ids 和 reasoning_type(direct/inference)。
    每项结论必须能由其 citation_ids 对应证据直接支持，禁止仅挂一个不相关引用。证据冲突时不得选边，必须列入 insufficient_evidence。
    仅输出 JSON：claims, insufficient_evidence, suggested_materials, follow_up_questions, conversation_summary。
当前网页上下文：{page_context_text}
已有会话摘要：{conversation_summary or "暂无"}
证据：\n{evidence_text}"""
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in (history or [])[-8:]:
        role = item.get("role")
        content = item.get("content", "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[-3000:]})
    messages.append({"role": "user", "content": question})
    with httpx.Client(timeout=60) as client:
        response = client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "response_format": {"type": "json_object"}, "temperature": 0.1,
                  "messages": messages},
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("DeepSeek 未返回可验证的结构化答案") from exc
    allowed = {item["chunk_id"] for item in citations}
    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("模型未返回逐结论引用，答案已拦截")
    used: set[int] = set()
    answer_parts: list[str] = []
    reasoning_types: set[str] = set()
    for claim in claims:
        text = str(claim.get("text", "")).strip() if isinstance(claim, dict) else ""
        raw_ids = claim.get("citation_ids", []) if isinstance(claim, dict) else []
        claim_ids = {int(str(value).lstrip("C")) for value in raw_ids if str(value).lstrip("C").isdigit()}
        reasoning_type = claim.get("reasoning_type") if isinstance(claim, dict) else None
        if not text or not claim_ids or not claim_ids.issubset(allowed) or reasoning_type not in {"direct", "inference"}:
            raise ValueError("模型返回了无依据结论或无效引用，答案已拦截")
        used.update(claim_ids)
        reasoning_types.add(reasoning_type)
        answer_parts.append(text)
    selected = [item for item in citations if item["chunk_id"] in used]
    return {
        "answer": "\n\n".join(answer_parts), "citations": selected,
        "reasoning_type": "inference" if "inference" in reasoning_types else "direct", "grounded": True,
        "insufficient_evidence": data.get("insufficient_evidence", []),
        "suggested_materials": data.get("suggested_materials", []),
        "follow_up_questions": data.get("follow_up_questions", []),
        "conversation_summary": str(data.get("conversation_summary", ""))[:2000],
    }
