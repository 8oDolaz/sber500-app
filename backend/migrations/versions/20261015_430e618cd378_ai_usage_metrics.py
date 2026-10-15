"""all-time AI usage

metrics_ai_usage: one row, all time, from the llm_usage ledger. Product calls only (feature
"extraction": every message or photo sent to the bot); no fake LLM, no evals or llm-ping, no test users.

- users_called_ai: unique users whose request reached the model, whatever the outcome;
- users_got_ai_answer: unique users with at least one successful model answer;
- ai_calls: model calls in total (a timeout or rate limit is retried once and counts twice).

Revision ID: 430e618cd378
Revises: 361a76071bab
Create Date: 2026-10-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "430e618cd378"
down_revision: str | Sequence[str] | None = "361a76071bab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW = """
    SELECT count(DISTINCT l.user_id) AS users_called_ai,
           count(DISTINCT l.user_id) FILTER (WHERE l.status = 'ok') AS users_got_ai_answer,
           count(*) AS ai_calls
    FROM llm_usage l
    JOIN users u ON u.id = l.user_id
    WHERE l.feature = 'extraction' AND l.provider <> 'fake' AND NOT u.is_test
"""


def upgrade() -> None:
    op.execute(f"CREATE VIEW metrics_ai_usage AS {VIEW}")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS metrics_ai_usage")
