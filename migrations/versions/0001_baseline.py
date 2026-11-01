"""Baseline schema (all tables + indexes from app.db.models).

Later schema changes: edit models.py, then `alembic revision --autogenerate -m "msg"` and `alembic upgrade head`.
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    from app.db.models import Base
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    from app.db.models import Base
    Base.metadata.drop_all(bind=op.get_bind())
