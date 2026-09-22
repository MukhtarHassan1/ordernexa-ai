"""Create transaction core

Revision ID: 0001_transaction_core
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_transaction_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE SEQUENCE transaction_public_id_seq START WITH 1"
    )

    op.create_table(
        "transactions",

        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "public_id",
            sa.String(length=32),
            nullable=False,
        ),

        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "intent",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),

        sa.Column(
            "value",
            sa.Numeric(18, 2),
            nullable=True,
        ),

        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),

        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="RECEIVED",
        ),

        sa.Column(
            "risk",
            sa.String(length=20),
            nullable=False,
            server_default="LOW",
        ),

        sa.Column(
            "autonomy_level",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_transactions_public_id",
        "transactions",
        ["public_id"],
        unique=True,
    )

    op.create_index(
        "ix_transactions_status",
        "transactions",
        ["status"],
    )

    op.create_table(
        "transaction_events",

        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "transactions.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),

        sa.Column(
            "step",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "actor_type",
            sa.String(length=30),
            nullable=False,
            server_default="SYSTEM",
        ),

        sa.Column(
            "actor_id",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),

        sa.Column(
            "payload_hash",
            sa.String(length=64),
            nullable=True,
        ),

        sa.Column(
            "trace_id",
            sa.String(length=64),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_transaction_events_transaction_id",
        "transaction_events",
        ["transaction_id"],
    )

    op.create_index(
        "ix_transaction_events_event_type",
        "transaction_events",
        ["event_type"],
    )

    op.create_index(
        "ix_transaction_events_trace_id",
        "transaction_events",
        ["trace_id"],
    )


def downgrade() -> None:
    op.drop_table(
        "transaction_events"
    )

    op.drop_table(
        "transactions"
    )

    op.execute(
        "DROP SEQUENCE IF EXISTS transaction_public_id_seq"
    )