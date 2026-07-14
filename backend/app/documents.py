import re
from pathlib import Path

import fitz
from docx import Document as DocxDocument


def _split(text: str, locator: str, heading: str | None = None, size: int = 900) -> list[dict]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks, buffer = [], ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) > size and buffer:
            chunks.append({"content": buffer, "locator": locator, "heading": heading})
            buffer = ""
        buffer = f"{buffer}\n{paragraph}".strip()
    if buffer:
        chunks.append({"content": buffer, "locator": locator, "heading": heading})
    return chunks


def parse_document(path: Path, suffix: str) -> list[dict]:
    suffix = suffix.lower()
    result: list[dict] = []
    if suffix == ".pdf":
        with fitz.open(path) as pdf:
            for index, page in enumerate(pdf):
                result.extend(_split(page.get_text("text"), f"第 {index + 1} 页"))
    elif suffix == ".docx":
        doc = DocxDocument(path)
        heading = None
        paragraph_no = 0
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            paragraph_no += 1
            if paragraph.style and paragraph.style.name.startswith("Heading"):
                heading = text
            result.extend(_split(text, f"第 {paragraph_no} 段", heading, 900))
    elif suffix in {".txt", ".md", ".markdown"}:
        content = path.read_text(encoding="utf-8-sig")
        heading = None
        for index, block in enumerate(re.split(r"\n\s*\n", content), 1):
            first = block.strip().splitlines()[0] if block.strip() else ""
            if suffix != ".txt" and first.startswith("#"):
                heading = first.lstrip("# ")
            result.extend(_split(block, f"第 {index} 段", heading))
    else:
        raise ValueError("仅支持 PDF、DOCX、TXT 和 Markdown 文件")
    if not result:
        raise ValueError("未提取到可用文字；扫描版 PDF 暂不支持 OCR")
    return result
