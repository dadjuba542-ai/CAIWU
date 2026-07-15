import json
import re
import statistics
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import fitz
import httpx
from docx import Document as DocxDocument
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .database import SessionLocal
from .models import (
    AIProviderSetting, Chapter, CurriculumProposal, Document, DocumentChunk,
    KnowledgePoint, ProposalNode, Subject,
)


HEADING_PATTERN = re.compile(
    r"^(第[一二三四五六七八九十百0-9]+[章节篇部]|[一二三四五六七八九十]+[、.]|\d+(?:\.\d+){0,3}[、.\s]|[（(][一二三四五六七八九十0-9]+[）)])"
)


@dataclass
class HeadingCandidate:
    level: int
    title: str
    locator: str
    confidence: float


def _clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n.-·•")[:180]


def extract_headings(path: Path, suffix: str) -> list[HeadingCandidate]:
    suffix = suffix.lower()
    if suffix == ".pdf":
        return _pdf_headings(path)
    if suffix == ".docx":
        result = []
        doc = DocxDocument(path)
        paragraph_no = 0
        for paragraph in doc.paragraphs:
            text = _clean_title(paragraph.text)
            if not text:
                continue
            paragraph_no += 1
            style = paragraph.style.name if paragraph.style else ""
            match = re.search(r"Heading\s*(\d+)|标题\s*(\d+)", style, re.I)
            if match:
                level = int(match.group(1) or match.group(2) or 1)
                result.append(HeadingCandidate(level, text, f"第 {paragraph_no} 段", 0.96))
            elif HEADING_PATTERN.match(text) and len(text) <= 70:
                level = 2 if re.match(r"^\d+\.\d+", text) else 1
                result.append(HeadingCandidate(level, text, f"第 {paragraph_no} 段", 0.72))
        return result
    content = path.read_text(encoding="utf-8-sig")
    result = []
    paragraph_no = 0
    for block in re.split(r"\n\s*\n", content):
        text = block.strip()
        if not text:
            continue
        paragraph_no += 1
        first = _clean_title(text.splitlines()[0])
        if suffix in {".md", ".markdown"} and first.startswith("#"):
            hashes = len(first) - len(first.lstrip("#"))
            result.append(HeadingCandidate(hashes, _clean_title(first.lstrip("#")), f"第 {paragraph_no} 段", 0.98))
        elif HEADING_PATTERN.match(first) and len(first) <= 70:
            level = 2 if re.match(r"^\d+\.\d+", first) else 1
            result.append(HeadingCandidate(level, first, f"第 {paragraph_no} 段", 0.76))
    return result


def _pdf_headings(path: Path) -> list[HeadingCandidate]:
    with fitz.open(path) as pdf:
        toc = pdf.get_toc(simple=True)
        if toc:
            return [HeadingCandidate(max(1, int(level)), _clean_title(title), f"第 {page} 页", 0.99)
                    for level, title, page in toc if _clean_title(title)]
        lines: list[tuple[float, str, int]] = []
        body_sizes: list[float] = []
        for page_index, page in enumerate(pdf):
            for block in page.get_text("dict").get("blocks", []):
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    spans = line.get("spans", [])
                    text = _clean_title("".join(span.get("text", "") for span in spans))
                    if not text:
                        continue
                    size = max((float(span.get("size", 0)) for span in spans), default=0)
                    body_sizes.extend(float(span.get("size", 0)) for span in spans if span.get("text", "").strip())
                    if len(text) <= 70:
                        lines.append((size, text, page_index + 1))
        body = statistics.median(body_sizes) if body_sizes else 10
        heading_sizes = sorted({round(size, 1) for size, text, _ in lines if size >= body * 1.16 or HEADING_PATTERN.match(text)}, reverse=True)
        result = []
        for size, text, page in lines:
            numbered = bool(HEADING_PATTERN.match(text))
            if size < body * 1.16 and not numbered:
                continue
            level = heading_sizes.index(round(size, 1)) + 1 if round(size, 1) in heading_sizes else 1
            if re.match(r"^\d+\.\d+", text):
                level = max(2, level)
            result.append(HeadingCandidate(min(level, 4), text, f"第 {page} 页", 0.82 if size >= body * 1.16 else 0.68))
        return result


def _chunks_for_heading(
    chunks: list[DocumentChunk], headings: list[HeadingCandidate], heading_index: int,
) -> list[int]:
    """关联标题至下一个同级/更高标题前的完整正文范围。"""
    heading = headings[heading_index]
    exact = [chunk for chunk in chunks if chunk.locator == heading.locator]
    if not exact:
        return [chunks[0].id] if chunks else []
    start = min(chunk.position for chunk in exact)
    end = None
    for candidate in headings[heading_index + 1:]:
        if candidate.level > heading.level:
            continue
        positions = [chunk.position for chunk in chunks if chunk.locator == candidate.locator]
        if positions:
            end = min(positions)
            break
    return [chunk.id for chunk in chunks if chunk.position >= start and (end is None or chunk.position < end)]


def mechanical_tree(document: Document, chunks: list[DocumentChunk]) -> list[dict]:
    headings = extract_headings(Path(document.path), Path(document.path).suffix)
    if not headings:
        points = []
        for chunk in chunks[:6]:
            first = _clean_title(chunk.content.splitlines()[0])
            if first:
                points.append({"title": first[:60], "original_title": first[:60], "position": len(points),
                               "confidence": 0.38, "source_chunk_ids": [chunk.id], "source_locators": [chunk.locator]})
        return [{"title": document.name, "original_title": document.name, "position": 0, "confidence": 0.35,
                 "source_chunk_ids": [chunk.id for chunk in chunks[:1]],
                 "source_locators": [chunk.locator for chunk in chunks[:1]], "points": points}]
    base_level = min(item.level for item in headings)
    chapters: list[dict] = []
    current = None
    for heading_index, heading in enumerate(headings):
        source_ids = _chunks_for_heading(chunks, headings, heading_index)
        common = {"title": heading.title, "original_title": heading.title, "confidence": heading.confidence,
                  "source_chunk_ids": source_ids, "source_locators": [heading.locator]}
        if heading.level == base_level or current is None:
            current = {**common, "position": len(chapters), "points": []}
            chapters.append(current)
        else:
            current["points"].append({**common, "position": len(current["points"])})
    for chapter in chapters:
        if not chapter["points"]:
            chapter["points"].append({
                "title": f"核心内容：{chapter['title']}", "original_title": chapter["title"], "position": 0,
                "confidence": max(0.4, chapter["confidence"] - 0.2),
                "source_chunk_ids": chapter["source_chunk_ids"], "source_locators": chapter["source_locators"],
            })
    return chapters


def _normal(value: str) -> str:
    return re.sub(r"[\s、，。:：()（）\-—_第章节篇部0-9一二三四五六七八九十]", "", value.lower())


def _best_match(title: str, rows: list[Chapter] | list[KnowledgePoint], threshold: float) -> int | None:
    normalized = _normal(title)
    best_id, best_score = None, 0.0
    for row in rows:
        score = SequenceMatcher(None, normalized, _normal(row.name)).ratio()
        if score > best_score:
            best_id, best_score = row.id, score
    return best_id if best_score >= threshold else None


def _enhance_with_deepseek(db: Session, document: Document, tree: list[dict], chunks: list[DocumentChunk]) -> tuple[list[dict], str | None, str | None]:
    setting = db.get(AIProviderSetting, 1)
    if not setting or not setting.encrypted_key:
        return tree, None, "未配置 DeepSeek，已生成规则目录，可稍后重新增强。"
    key, migrated = settings.decrypt_secret(setting.encrypted_key)
    if migrated:
        setting.encrypted_key = migrated
        db.commit()
    allowed = {chunk.id for chunk in chunks}
    evidence = [{"chunk_id": chunk.id, "locator": chunk.locator, "text": chunk.content[:500]} for chunk in chunks[:24]]
    prompt = {
        "rule_outline": tree, "evidence": evidence,
        "requirements": ["保留原资料章节顺序", "仅规范标题并补充资料中明确出现的知识点", "每个节点必须列出source_chunk_ids", "不得引入证据外知识"],
        "schema": {"chapters": [{"title": "", "source_chunk_ids": [1], "points": [{"title": "", "source_chunk_ids": [1]}]}]},
    }
    try:
        response = httpx.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}"}, timeout=60,
            json={"model": setting.model, "temperature": 0.05, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": "你是课程结构整理器，只能基于输入证据输出JSON。"},
                               {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}]},
        )
        response.raise_for_status()
        data = json.loads(response.json()["choices"][0]["message"]["content"])
        enhanced = []
        for chapter in data.get("chapters", []):
            source_ids = [int(x) for x in chapter.get("source_chunk_ids", []) if int(x) in allowed]
            if not chapter.get("title") or not source_ids:
                continue
            chunk_map = {chunk.id: chunk for chunk in chunks}
            points = []
            for point in chapter.get("points", []):
                point_ids = [int(x) for x in point.get("source_chunk_ids", []) if int(x) in allowed]
                if point.get("title") and point_ids:
                    points.append({"title": _clean_title(point["title"]), "original_title": _clean_title(point["title"]),
                                   "position": len(points), "confidence": 0.82, "source_chunk_ids": point_ids,
                                   "source_locators": list(dict.fromkeys(chunk_map[x].locator for x in point_ids))})
            enhanced.append({"title": _clean_title(chapter["title"]), "original_title": _clean_title(chapter["title"]),
                             "position": len(enhanced), "confidence": 0.86, "source_chunk_ids": source_ids,
                             "source_locators": list(dict.fromkeys(chunk_map[x].locator for x in source_ids)), "points": points})
        return (enhanced or tree), setting.model, None if enhanced else "AI 输出无有效来源，已保留规则目录。"
    except Exception:
        return tree, setting.model, "DeepSeek 增强失败，已保留规则目录，可稍后重试。"


def process_outline(proposal_id: int) -> None:
    with SessionLocal() as db:
        proposal = db.get(CurriculumProposal, proposal_id)
        if not proposal:
            return
        document = db.get(Document, proposal.document_id)
        if not document or document.parse_status != "ready":
            proposal.status = "failed"; proposal.error = "资料尚未完成文字解析"; db.commit(); return
        try:
            proposal.status = "extracting"; proposal.error = None; document.outline_status = "extracting"; db.commit()
            chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document.id).order_by(DocumentChunk.position)).all()
            tree = mechanical_tree(document, chunks)
            proposal.status = "enhancing"; document.outline_status = "enhancing"; db.commit()
            tree, model, warning = _enhance_with_deepseek(db, document, tree, chunks)
            db.query(ProposalNode).filter(ProposalNode.proposal_id == proposal.id).delete()
            subject = db.scalar(select(Subject).where(Subject.id == proposal.subject_id).options(selectinload(Subject.chapters).selectinload(Chapter.points)))
            chapter_count = point_count = merge_count = 0
            for chapter_data in tree:
                target = _best_match(chapter_data["title"], subject.chapters if subject else [], 0.78)
                chapter = ProposalNode(
                    proposal_id=proposal.id, node_type="chapter", title=chapter_data["title"], original_title=chapter_data["original_title"],
                    position=chapter_count, confidence=chapter_data["confidence"], source_chunk_ids=chapter_data["source_chunk_ids"],
                    source_locators=chapter_data["source_locators"], action="merge" if target else "create", target_node_id=target,
                )
                db.add(chapter); db.flush(); chapter_count += 1; merge_count += int(bool(target))
                existing_points = next((row.points for row in subject.chapters if row.id == target), []) if subject and target else []
                for point_data in chapter_data.get("points", []):
                    point_target = _best_match(point_data["title"], existing_points, 0.82)
                    db.add(ProposalNode(
                        proposal_id=proposal.id, parent_id=chapter.id, node_type="point", title=point_data["title"],
                        original_title=point_data["original_title"], position=point_data["position"], confidence=point_data["confidence"],
                        source_chunk_ids=point_data["source_chunk_ids"], source_locators=point_data["source_locators"],
                        action="merge" if point_target else "create", target_node_id=point_target,
                    ))
                    point_count += 1; merge_count += int(bool(point_target))
            proposal.status = "review"; proposal.ai_enhanced = bool(model and not warning); proposal.model = model
            proposal.warning = warning; proposal.result_summary = {"chapters": chapter_count, "points": point_count, "merge_suggestions": merge_count}
            document.outline_status = "review"; db.commit()
        except Exception as exc:
            db.rollback()
            proposal = db.get(CurriculumProposal, proposal_id)
            document = db.get(Document, proposal.document_id) if proposal else None
            if proposal: proposal.status = "failed"; proposal.error = str(exc)[:500]
            if document: document.outline_status = "failed"
            db.commit()
