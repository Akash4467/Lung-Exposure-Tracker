"""Auth: email/password and Google identities, refresh tokens, one-time email codes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UP = [
    "ALTER TABLE users ADD COLUMN email citext UNIQUE",
    "ALTER TABLE users ADD COLUMN email_verified boolean NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN password_hash text",
    "ALTER TABLE users ADD COLUMN google_sub text UNIQUE",
    "ALTER TABLE users ADD COLUMN last_login_at timestamptz",
    # Refresh tokens are stored hashed. A family is one sign-in; every refresh rotates the
    # token within the family. Presenting a used token revokes the whole family.
    """
    CREATE TABLE refresh_tokens (
      id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      family_id    uuid NOT NULL,
      token_hash   bytea NOT NULL UNIQUE,
      expires_at   timestamptz NOT NULL,
      used_at      timestamptz,
      revoked_at   timestamptz,
      created_at   timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX refresh_tokens_family ON refresh_tokens (family_id)",
    "CREATE INDEX refresh_tokens_user ON refresh_tokens (user_id)",
    # 6-digit codes for email verification and password reset, stored hashed.
    """
    CREATE TABLE email_codes (
      user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      purpose     text NOT NULL CHECK (purpose IN ('verify_email','reset_password')),
      code_hash   bytea NOT NULL,
      attempts    smallint NOT NULL DEFAULT 0,
      expires_at  timestamptz NOT NULL,
      created_at  timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, purpose)
    )
    """,
]

DOWN = [
    "DROP TABLE IF EXISTS email_codes",
    "DROP TABLE IF EXISTS refresh_tokens",
    "ALTER TABLE users DROP COLUMN IF EXISTS last_login_at",
    "ALTER TABLE users DROP COLUMN IF EXISTS google_sub",
    "ALTER TABLE users DROP COLUMN IF EXISTS password_hash",
    "ALTER TABLE users DROP COLUMN IF EXISTS email_verified",
    "ALTER TABLE users DROP COLUMN IF EXISTS email",
]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
