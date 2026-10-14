"""all-time user totals

Read straight from the tables (not from analytics events), so the numbers match the database
exactly. Like every metrics view, they exclude test and load-test accounts (users.is_test).

- metrics_user_totals: one row, all time: registered users, users active at least once (ADR 0003),
  families with at least one real member.
- metrics_user_growth: registered users per reporting day (Europe/Moscow) and the running total.

Revision ID: 361a76071bab
Revises: afdde21e679f
Create Date: 2026-10-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "361a76071bab"
down_revision: str | Sequence[str] | None = "afdde21e679f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = "'Europe/Moscow'"

VIEWS: list[tuple[str, str]] = [
    (
        "metrics_user_totals",
        """
        SELECT (SELECT count(*) FROM users WHERE NOT is_test) AS registered_users,
               (SELECT count(DISTINCT user_id) FROM analytics_real_activity) AS active_users,
               (SELECT count(DISTINCT m.family_id)
                FROM members m JOIN users u ON u.id = m.user_id
                WHERE NOT u.is_test) AS families
        """,
    ),
    (
        "metrics_user_growth",
        f"""
        SELECT day, new_users, sum(new_users) OVER (ORDER BY day) AS total_users
        FROM (
            SELECT (created_at AT TIME ZONE {TZ})::date AS day, count(*) AS new_users
            FROM users
            WHERE NOT is_test
            GROUP BY 1
        ) d
        """,
    ),
]


def upgrade() -> None:
    for name, sql in VIEWS:
        op.execute(f"CREATE VIEW {name} AS {sql}")


def downgrade() -> None:
    for name, _ in reversed(VIEWS):
        op.execute(f"DROP VIEW IF EXISTS {name}")
