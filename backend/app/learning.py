import hashlib
import math
import re
from collections import Counter
from datetime import date, timedelta
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from .models import KnowledgePoint, ReviewItem


VECTOR_SIZE = 256


def tokenize(text: str) -> list[str]:
    chinese = re.findall(r"[\u4e00-\u9fff]", text.lower())
    words = re.findall(r"[a-z0-9_]{2,}", text.lower())
    return chinese + words


def embed(text: str) -> list[float]:
    vector = [0.0] * VECTOR_SIZE
    for token, count in Counter(tokenize(text)).items():
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % VECTOR_SIZE
        vector[index] += count * (1 if digest[4] % 2 else -1)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


_ASSESSMENT_STOP_TERMS = {
    "以及", "但是", "因此", "可以", "需要", "应当", "如果", "因为", "所以", "对于", "根据",
    "其中", "相关", "进行", "一个", "这个", "那个", "是否", "能够", "属于", "包括", "不得",
}


def _assessment_terms(text: str) -> set[str]:
    """提取简答题评分用的短语，避免把整段答案拆成单字集合。"""
    normalized = re.sub(r"\s+", "", text.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]+", normalized)
    bigrams = {
        part[index:index + 2]
        for part in chinese
        for index in range(max(0, len(part) - 1))
        if part[index:index + 2] not in _ASSESSMENT_STOP_TERMS
    }
    words = set(re.findall(r"[a-z0-9_]{2,}", normalized))
    return bigrams | words


def score_short_answer(expected: str, actual: str, topic: str = "") -> float:
    """按关键短语覆盖率和整体相似度评分，返回 0 到 1。"""
    expected_text = f"{topic} {expected}".strip()
    expected_base = re.sub(r"\s+", "", expected.lower())
    expected_normalized = re.sub(r"\s+", "", expected_text.lower())
    actual_normalized = re.sub(r"\s+", "", actual.lower())
    if not actual_normalized or not expected_normalized:
        return 0.0
    if actual_normalized in {expected_normalized, expected_base}:
        return 1.0
    expected_terms = _assessment_terms(expected_text)
    actual_terms = _assessment_terms(actual)
    phrase_score = len(expected_terms & actual_terms) / max(1, len(expected_terms))
    sequence_score = SequenceMatcher(None, expected_normalized, actual_normalized).ratio()
    return round(min(1.0, phrase_score * 0.7 + sequence_score * 0.3), 2)


def schedule_review(db: Session, item: ReviewItem, quality: int) -> ReviewItem:
    item.attempts += 1
    if quality < 3:
        item.interval_days = 1
    elif item.attempts == 1:
        item.interval_days = 2
    elif item.attempts == 2:
        item.interval_days = 6
    else:
        item.interval_days = min(120, round(item.interval_days * (1.3 + quality * 0.18)))
    item.due_date = date.today() + timedelta(days=item.interval_days)
    point = db.get(KnowledgePoint, item.knowledge_point_id)
    if point:
        point.mastery = max(0, min(100, point.mastery + (quality - 2) * 8))
        point.status = "mastered" if point.mastery >= 85 else "reviewing"
    db.commit()
    db.refresh(item)
    return item
