"""photo captures in metrics_ai_quality

Photos are captured through the vision model since ADR 0005: count them as captures, not as
unsupported content, and break them out in a new `captures_photo` column (appended, so
CREATE OR REPLACE keeps the view and Grafana's grants).

Revision ID: afdde21e679f
Revises: a1c9e5f0b7d2
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "afdde21e679f"
down_revision: str | Sequence[str] | None = "a1c9e5f0b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPPORTED = "('text', 'photo')"

COUNTS = """
        count(*) FILTER (WHERE name = 'draft_action_created' AND properties->>'model' IS NOT NULL) AS drafts_ai,
        count(*) FILTER (WHERE name = 'draft_action_created' AND properties->>'model' IS NULL) AS drafts_raw,
        count(*) FILTER (WHERE name = 'draft_action_confirmed') AS confirmed,
        count(*) FILTER (WHERE name = 'draft_action_revised') AS revised,
        count(*) FILTER (WHERE name = 'draft_action_cancelled') AS cancelled,
        count(*) FILTER (WHERE name = 'draft_action_expired') AS expired,
        count(*) FILTER (WHERE name = 'capture_failed' AND properties->>'reason' = 'no_items') AS failed_no_items,
        count(*) FILTER (WHERE name = 'capture_failed' AND properties->>'reason' <> 'no_items') AS failed_llm,
        round(
            count(*) FILTER (WHERE name = 'draft_action_confirmed')::numeric
            / nullif(count(*) FILTER (WHERE name = 'draft_action_created'), 0), 3
        ) AS confirm_rate"""

SOURCE = """
    FROM analytics_real_events
    WHERE name IN ('capture_received', 'capture_failed', 'draft_action_created', 'draft_action_confirmed',
                   'draft_action_revised', 'draft_action_cancelled', 'draft_action_expired')
    GROUP BY 1"""

NEW = f"""
    SELECT day,
        count(*) FILTER (WHERE name = 'capture_received' AND properties->>'content_type' IN {SUPPORTED}) AS captures,
        count(*) FILTER (WHERE name = 'capture_received'
                         AND properties->>'content_type' NOT IN {SUPPORTED}) AS captures_unsupported,
        {COUNTS},
        count(*) FILTER (WHERE name = 'capture_received' AND properties->>'content_type' = 'photo') AS captures_photo
    {SOURCE}
"""

OLD = f"""
    SELECT day,
        count(*) FILTER (WHERE name = 'capture_received' AND properties->>'content_type' = 'text') AS captures,
        count(*) FILTER (WHERE name = 'capture_received'
                         AND properties->>'content_type' <> 'text') AS captures_unsupported,
        {COUNTS}
    {SOURCE}
"""


def upgrade() -> None:
    op.execute(f"CREATE OR REPLACE VIEW metrics_ai_quality AS {NEW}")


def downgrade() -> None:
    # CREATE OR REPLACE can't drop a column: recreate, then restore Grafana's read grant if its role exists.
    op.execute("DROP VIEW metrics_ai_quality")
    op.execute(f"CREATE VIEW metrics_ai_quality AS {OLD}")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_reader') THEN "
        "GRANT SELECT ON metrics_ai_quality TO grafana_reader; END IF; END $$"
    )
