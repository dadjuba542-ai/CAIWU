from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0001_platform_v2"
down_revision = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    from app.database import Base
    from app import models  # noqa: F401
    Base.metadata.create_all(bind)
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("document_chunks")}
    additions = {
        "vector": sa.Column("vector", Vector(512), nullable=True),
        "embedding_model": sa.Column("embedding_model", sa.String(120), nullable=True),
        "index_version": sa.Column("index_version", sa.Integer(), server_default="1", nullable=False),
        "content_hash": sa.Column("content_hash", sa.String(64), nullable=True),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("document_chunks", column)
    if bind.dialect.name == "postgresql":
        op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_vector_hnsw ON document_chunks USING hnsw (vector vector_cosine_ops)")


def downgrade():
    raise RuntimeError("平台 v2 迁移不可自动降级，请从迁移前备份恢复")
