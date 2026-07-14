import hashlib
import math
import re
from collections import Counter
from datetime import date, timedelta

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
