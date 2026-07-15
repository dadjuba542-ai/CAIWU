import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .documents import parse_document
from .embeddings import content_hash, semantic_embed
from .jobs import claim
from .models import CurriculumProposal, Document, DocumentChunk, ProcessingJob
from .outlines import process_outline


def process(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if not job or job.status == "cancelled": return
        document = db.get(Document, int(job.payload["document_id"]))
        if not document: raise ValueError("资料不存在")
        if job.job_type in {"parse_document", "reindex_document"}:
            chunks = parse_document(Path(document.path), Path(document.path).suffix)
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
            total = len(chunks)
            for index, chunk in enumerate(chunks):
                vector = semantic_embed(chunk["content"])
                db.add(DocumentChunk(document_id=document.id, position=index, embedding=vector, vector=vector,
                    embedding_model=settings.embedding_model, content_hash=content_hash(chunk["content"]), **chunk))
                job.progress = int((index + 1) / total * 80); job.heartbeat_at = datetime.utcnow(); db.commit()
            document.status = document.parse_status = "ready"; document.outline_status = "extracting"
            proposal = CurriculumProposal(document_id=document.id, subject_id=document.subject_id, status="extracting")
            db.add(proposal); db.commit(); db.refresh(proposal)
            process_outline(proposal.id)
        elif job.job_type == "outline_document":
            process_outline(int(job.payload["proposal_id"]))
        elif job.job_type == "backfill_vectors":
            chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.vector.is_(None)).order_by(DocumentChunk.id)).all()
            total = len(chunks)
            for index, chunk in enumerate(chunks):
                vector = semantic_embed(chunk.content); chunk.vector = vector; chunk.embedding = vector
                chunk.embedding_model = settings.embedding_model; chunk.content_hash = content_hash(chunk.content)
                job.progress = int((index + 1) / max(1, total) * 100); job.heartbeat_at = datetime.utcnow(); db.commit()
        job.status = "completed"; job.progress = 100; job.error = None; db.commit()


def run() -> None:
    while True:
        with SessionLocal() as db:
            job = claim(db)
        if not job:
            time.sleep(settings.worker_poll_seconds); continue
        try:
            process(job.id)
        except Exception as exc:
            with SessionLocal() as db:
                failed = db.get(ProcessingJob, job.id)
                if failed:
                    failed.error = str(exc)[:1000]
                    failed.status = "queued" if failed.attempts < failed.max_attempts else "failed"
                    failed.locked_at = None; db.commit()


if __name__ == "__main__":
    run()
