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
    query_vec = embed(question)
    query_tokens = set(tokenize(question))
    ranked = []
    for chunk, document in db.execute(stmt).all():
        lexical = len(query_tokens.intersection(tokenize(chunk.content))) / max(1, len(query_tokens))
        score = cosine(query_vec, chunk.embedding) * 0.65 + lexical * 0.35
        ranked.append((score, chunk, document))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item for item in ranked[:limit] if item[0] >= 0.08]


def decrypt_key(db: Session) -> tuple[str, str]:
    row = db.get(AIProviderSetting, 1)
    if not row or not row.encrypted_key:
        raise ValueError("请先在设置中配置 DeepSeek API Key")
    return settings.fernet().decrypt(row.encrypted_key.encode()).decode(), row.model


def grounded_answer(db: Session, question: str, subject_id: int | None, chapter_id: int | None, mode: str) -> dict[str, Any]:
    evidence = retrieve(db, question, subject_id, chapter_id)
    citations = [
        {"chunk_id": chunk.id, "document_id": doc.id, "document_name": doc.name, "locator": chunk.locator, "quote": chunk.content[:220]}
        for _, chunk, doc in evidence
    ]
    if not citations:
        return {
            "answer": "当前资料不足以回答这个问题。请上传或绑定包含相关知识点的教材、讲义或法规资料。",
            "citations": [], "reasoning_type": "insufficient", "grounded": False,
            "insufficient_evidence": ["没有检索到与问题直接相关的资料片段"],
            "suggested_materials": ["相关科目的教材章节", "适用的法规或考试讲义"],
            "follow_up_questions": [],
        }
    api_key, model = decrypt_key(db)
    evidence_text = "\n\n".join(f"[C{item['chunk_id']}] {item['document_name']} {item['locator']}\n{item['quote']}" for item in citations)
    mode_instruction = "使用苏格拉底式追问，不直接给最终结论。" if mode == "socratic" else "直接、分层地回答。"
    system = f"""你是严谨的财务考证助教。你只能使用下方证据，不得使用常识补充。{mode_instruction}
关键结论必须引用 [C数字]。证据不足时必须明确拒答。
仅输出 JSON：answer, citation_ids, reasoning_type(direct/inference), insufficient_evidence, suggested_materials, follow_up_questions。
证据：\n{evidence_text}"""
    with httpx.Client(timeout=60) as client:
        response = client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "response_format": {"type": "json_object"}, "temperature": 0.1,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}]},
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("DeepSeek 未返回可验证的结构化答案") from exc
    allowed = {item["chunk_id"] for item in citations}
    used = {int(str(value).lstrip("C")) for value in data.get("citation_ids", []) if str(value).lstrip("C").isdigit()}
    if not used or not used.issubset(allowed):
        raise ValueError("模型返回了无效引用，答案已拦截")
    selected = [item for item in citations if item["chunk_id"] in used]
    return {
        "answer": data.get("answer", ""), "citations": selected,
        "reasoning_type": data.get("reasoning_type", "direct"), "grounded": True,
        "insufficient_evidence": data.get("insufficient_evidence", []),
        "suggested_materials": data.get("suggested_materials", []),
        "follow_up_questions": data.get("follow_up_questions", []),
    }
