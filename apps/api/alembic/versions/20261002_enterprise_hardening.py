"""OrderNexa enterprise hardening: business dedupe, circuits, subscriptions, autonomy, worker fencing.

Revision ID: 20261002_hardening
Revises: 20260929_auto
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261002_hardening"
down_revision = "20260929_auto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_order_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalized_po", sa.String(length=120), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("amendment_of_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["amendment_of_transaction_id"], ["transactions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("customer_id", "normalized_po", "revision", name="uq_business_order_customer_po_revision"),
        sa.UniqueConstraint("transaction_id", name="uq_business_order_transaction_id"),
    )
    op.create_index("ix_business_order_lookup", "business_order_identities", ["customer_id", "normalized_po"], unique=False)
    op.create_index("ix_business_order_customer_id", "business_order_identities", ["customer_id"], unique=False)
    op.create_index("ix_business_order_fingerprint", "business_order_identities", ["content_fingerprint"], unique=False)
    op.create_index("ix_business_order_amendment_of", "business_order_identities", ["amendment_of_transaction_id"], unique=False)

    op.create_table(
        "integration_circuits",
        sa.Column("provider", sa.String(length=60), primary_key=True, nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="CLOSED"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("half_open_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_category", sa.String(length=50), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "external_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("subscription_id", sa.String(length=180), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="ACTIVE"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_state_hash", sa.String(length=64), nullable=True),
        sa.Column("delta_link", sa.Text(), nullable=True),
        sa.Column("lifecycle_event", sa.String(length=60), nullable=True),
        sa.Column("last_renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_delta_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "subscription_id", name="uq_external_subscription_provider_id"),
    )
    op.create_index("ix_external_subscriptions_provider", "external_subscriptions", ["provider"], unique=False)
    op.create_index("ix_external_subscriptions_expires_at", "external_subscriptions", ["expires_at"], unique=False)

    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=250), nullable=False),
        sa.Column("document_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("jurisdiction", sa.String(length=30), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="ACTIVE"),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_system", "source_id", name="uq_knowledge_source"),
    )
    op.create_index("ix_knowledge_documents_customer_id", "knowledge_documents", ["customer_id"], unique=False)
    op.create_index("ix_knowledge_documents_document_type", "knowledge_documents", ["document_type"], unique=False)
    op.create_index("ix_knowledge_documents_jurisdiction", "knowledge_documents", ["jurisdiction"], unique=False)
    op.create_index("ix_knowledge_documents_effective_from", "knowledge_documents", ["effective_from"], unique=False)
    op.create_index("ix_knowledge_documents_effective_to", "knowledge_documents", ["effective_to"], unique=False)
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"], unique=False)

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=180), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_document_chunk"),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"], unique=False)
    op.create_index("ix_knowledge_chunks_content_sha256", "knowledge_chunks", ["content_sha256"], unique=False)
    op.create_index(
        "ix_knowledge_chunks_fts", "knowledge_chunks",
        [sa.text("to_tsvector('english', content)")],
        unique=False, postgresql_using="gin"
    )

    op.create_table(
        "payment_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False, server_default="STRIPE_SANDBOX"),
        sa.Column("external_session_id", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("checkout_url_hash", sa.String(length=64), nullable=True),
        sa.Column("external_payment_intent_id", sa.String(length=180), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provider", "external_session_id", name="uq_payment_provider_session"),
    )
    op.create_index("ix_payment_records_transaction_id", "payment_records", ["transaction_id"], unique=False)
    op.create_index("ix_payment_records_status", "payment_records", ["status"], unique=False)

    op.create_table(
        "autonomy_policies",
        sa.Column("action", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("policy_version", sa.String(length=40), nullable=False, server_default="1.0"),
        sa.Column("max_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("allowed_risks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[\"LOW\"]'::jsonb")),
        sa.Column("require_verified_evidence", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("level >= 0 AND level <= 4", name="ck_autonomy_level_0_4"),
    )

    op.add_column("integration_commands", sa.Column("error_category", sa.String(length=50), nullable=True))
    op.create_index("ix_integration_commands_error_category", "integration_commands", ["error_category"], unique=False)

    op.add_column("automation_jobs", sa.Column("correlation_id", sa.String(length=128), nullable=True))
    op.add_column("automation_jobs", sa.Column("lease_token", sa.String(length=64), nullable=True))
    op.add_column("automation_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_jobs", sa.Column("error_category", sa.String(length=50), nullable=True))
    op.create_index("ix_automation_jobs_correlation_id", "automation_jobs", ["correlation_id"], unique=False)
    op.create_index("ix_automation_jobs_lease_token", "automation_jobs", ["lease_token"], unique=False)
    op.create_index("ix_automation_jobs_error_category", "automation_jobs", ["error_category"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_automation_jobs_error_category", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_correlation_id", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_lease_token", table_name="automation_jobs")
    op.drop_column("automation_jobs", "error_category")
    op.drop_column("automation_jobs", "heartbeat_at")
    op.drop_column("automation_jobs", "lease_token")
    op.drop_column("automation_jobs", "correlation_id")
    op.drop_index("ix_integration_commands_error_category", table_name="integration_commands")
    op.drop_column("integration_commands", "error_category")
    op.drop_table("autonomy_policies")
    op.drop_index("ix_payment_records_status", table_name="payment_records")
    op.drop_index("ix_payment_records_transaction_id", table_name="payment_records")
    op.drop_table("payment_records")
    op.drop_index("ix_knowledge_chunks_fts", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_content_sha256", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    for name in ["ix_knowledge_documents_status", "ix_knowledge_documents_effective_to", "ix_knowledge_documents_effective_from", "ix_knowledge_documents_jurisdiction", "ix_knowledge_documents_document_type", "ix_knowledge_documents_customer_id"]:
        op.drop_index(name, table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("ix_external_subscriptions_expires_at", table_name="external_subscriptions")
    op.drop_index("ix_external_subscriptions_provider", table_name="external_subscriptions")
    op.drop_table("external_subscriptions")
    op.drop_table("integration_circuits")
    op.drop_index("ix_business_order_amendment_of", table_name="business_order_identities")
    op.drop_index("ix_business_order_fingerprint", table_name="business_order_identities")
    op.drop_index("ix_business_order_customer_id", table_name="business_order_identities")
    op.drop_index("ix_business_order_lookup", table_name="business_order_identities")
    op.drop_table("business_order_identities")
