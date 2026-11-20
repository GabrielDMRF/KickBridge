"""Esquema inicial de KickBridge."""

from alembic import op
import sqlalchemy as sa

revision = "20261120_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "streamers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("kick_broadcaster_user_id", sa.BigInteger(), nullable=False),
        sa.Column("api_token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_streamers_name"),
        sa.UniqueConstraint("api_token_hash", name="uq_streamers_api_token_hash"),
    )
    op.create_index("ix_streamers_kick_broadcaster_user_id", "streamers", ["kick_broadcaster_user_id"])
    op.create_index("ix_streamers_status", "streamers", ["status"])

    op.create_table(
        "minecraft_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("streamer_id", sa.Integer(), sa.ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uuid", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("streamer_id", "uuid", name="uq_mc_streamer_uuid"),
    )
    op.create_index("ix_minecraft_accounts_streamer_id", "minecraft_accounts", ["streamer_id"])

    op.create_table(
        "kick_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("streamer_id", sa.Integer(), sa.ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("minecraft_account_id", sa.Integer(), sa.ForeignKey("minecraft_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kick_user_id", sa.BigInteger(), nullable=False),
        sa.Column("kick_username", sa.String(length=64), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("minecraft_account_id", name="uq_kick_minecraft_account"),
        sa.UniqueConstraint("streamer_id", "kick_user_id", name="uq_kick_streamer_user"),
    )
    op.create_index("ix_kick_accounts_streamer_id", "kick_accounts", ["streamer_id"])
    op.create_index("ix_kick_accounts_status", "kick_accounts", ["status"])

    op.create_table(
        "link_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("streamer_id", sa.Integer(), sa.ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("minecraft_uuid", sa.String(length=36), nullable=False),
        sa.Column("minecraft_username", sa.String(length=16), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("state_enc", sa.Text(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("verifier_enc", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code_hash", name="uq_link_sessions_code_hash"),
        sa.UniqueConstraint("state_hash", name="uq_link_sessions_state_hash"),
    )
    op.create_index("ix_link_sessions_streamer_id", "link_sessions", ["streamer_id"])
    op.create_index("ix_link_sessions_minecraft_uuid", "link_sessions", ["minecraft_uuid"])
    op.create_index("ix_link_sessions_expires_at", "link_sessions", ["expires_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("streamer_id", sa.Integer(), sa.ForeignKey("streamers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("minecraft_uuid", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_streamer_created", "audit_logs", ["streamer_id", "created_at"])

    op.create_table(
        "message_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("streamer_id", sa.Integer(), sa.ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("minecraft_uuid", sa.String(length=36), nullable=False),
        sa.Column("kick_user_id", sa.BigInteger(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("kick_status", sa.Integer(), nullable=True),
        sa.Column("kick_message_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_message_events_created_at", "message_events", ["created_at"])
    op.create_index("ix_message_streamer_player_created", "message_events", ["streamer_id", "minecraft_uuid", "created_at"])

    op.create_table(
        "request_nonces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("streamer_id", sa.Integer(), sa.ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("nonce_hash", name="uq_request_nonces_hash"),
    )
    op.create_index("ix_request_nonces_streamer_id", "request_nonces", ["streamer_id"])
    op.create_index("ix_request_nonces_expires_at", "request_nonces", ["expires_at"])


def downgrade() -> None:
    op.drop_table("request_nonces")
    op.drop_table("message_events")
    op.drop_table("audit_logs")
    op.drop_table("link_sessions")
    op.drop_table("kick_accounts")
    op.drop_table("minecraft_accounts")
    op.drop_table("streamers")
