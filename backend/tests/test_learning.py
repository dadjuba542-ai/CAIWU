from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.learning import cosine, embed, schedule_review, score_short_answer
from app.models import Chapter, KnowledgePoint, ReviewItem, Subject, ExamTrack


def test_embedding_prefers_related_finance_text():
    question = embed("递延所得税资产如何确认")
    related = embed("递延所得税资产的确认条件与可抵扣暂时性差异")
    unrelated = embed("审计抽样的样本规模")
    assert cosine(question, related) > cosine(question, unrelated)


def test_review_quality_updates_interval_and_mastery():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    exam = ExamTrack(name="注册会计师", code="CPA")
    db.add(exam); db.flush()
    subject = Subject(exam_id=exam.id, name="会计")
    db.add(subject); db.flush()
    chapter = Chapter(subject_id=subject.id, name="所得税")
    db.add(chapter); db.flush()
    point = KnowledgePoint(chapter_id=chapter.id, name="递延所得税", mastery=40)
    db.add(point); db.flush()
    review = ReviewItem(knowledge_point_id=point.id, prompt="解释概念", answer="参考答案", due_date=date.today())
    db.add(review); db.commit()
    result = schedule_review(db, review, 5)
    assert result.interval_days == 2
    assert point.mastery == 64
    assert result.due_date > date.today()


def test_short_answer_score_does_not_use_single_character_overlap():
    expected = "递延所得税资产需要在预计未来有足够应纳税所得额时确认。"
    assert score_short_answer(expected, "确认条件") < 0.5
    assert score_short_answer(expected, "递延所得税资产需要在预计未来有足够应纳税所得额时确认。", "递延所得税资产") == 1
