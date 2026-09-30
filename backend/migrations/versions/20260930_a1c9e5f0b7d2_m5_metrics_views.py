"""m5 metrics views

Product metrics for dashboards (Grafana → Postgres). Plain views: cheap at MVP volume; switch the
heavy ones to materialized views with a nightly refresh when they get slow (ARCHITECTURE §9.6).

Every view excludes:
- test users (users.is_test: e2e and load-test accounts) and anything they did before signing in
  (their anonymous_id);
- load-test traffic that never signs in (app_version = 'loadtest');
- the fake LLM provider and eval runs (llm_usage).
Days are reporting days in Europe/Moscow (ADR 0003).

Revision ID: a1c9e5f0b7d2
Revises: dc2f6a57da10
Create Date: 2026-09-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1c9e5f0b7d2"
down_revision: str | Sequence[str] | None = "dc2f6a57da10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = "'Europe/Moscow'"

VIEWS: list[tuple[str, str]] = [
    (
        "analytics_real_events",
        f"""
        WITH test_anon AS (
            SELECT DISTINCT e.anonymous_id
            FROM analytics_events e JOIN users u ON u.id = e.user_id
            WHERE u.is_test AND e.anonymous_id IS NOT NULL
        )
        SELECT e.*, (e.occurred_at AT TIME ZONE {TZ})::date AS day
        FROM analytics_events e
        LEFT JOIN users u ON u.id = e.user_id
        WHERE u.is_test IS NOT TRUE
          AND e.app_version IS DISTINCT FROM 'loadtest'
          AND (e.anonymous_id IS NULL OR e.anonymous_id NOT IN (SELECT anonymous_id FROM test_anon))
        """,
    ),
    (
        "analytics_real_activity",
        """
        SELECT a.*
        FROM user_activity_daily a JOIN users u ON u.id = a.user_id
        WHERE NOT u.is_test
        """,
    ),
    (
        "metrics_dau_by_platform",
        """
        SELECT activity_date AS day, platform, count(DISTINCT user_id) AS dau
        FROM analytics_real_activity
        GROUP BY 1, 2
        """,
    ),
    (
        "metrics_active_users",
        """
        WITH days AS (SELECT DISTINCT activity_date AS day FROM analytics_real_activity)
        SELECT d.day,
               (SELECT count(DISTINCT user_id) FROM analytics_real_activity WHERE activity_date = d.day) AS dau,
               (SELECT count(DISTINCT user_id) FROM analytics_real_activity
                 WHERE activity_date > d.day - 7 AND activity_date <= d.day) AS wau,
               (SELECT count(DISTINCT user_id) FROM analytics_real_activity
                 WHERE activity_date > d.day - 30 AND activity_date <= d.day) AS mau,
               (SELECT count(DISTINCT family_id) FROM analytics_real_activity
                 WHERE activity_date = d.day AND family_id IS NOT NULL) AS active_families
        FROM days d
        """,
    ),
    (
        "metrics_new_users",
        """
        SELECT day,
               properties->>'platform' AS platform,
               properties->>'acquisition_source' AS acquisition_source,
               count(*) AS new_users
        FROM analytics_real_events
        WHERE name = 'user_signed_up'
        GROUP BY 1, 2, 3
        """,
    ),
    (
        "metrics_new_families",
        """
        SELECT day, count(*) AS new_families
        FROM analytics_real_events
        WHERE name = 'family_created'
        GROUP BY 1
        """,
    ),
    (
        "metrics_registration_funnel",
        """
        WITH welcome AS (
            SELECT anonymous_id, min(day) AS day
            FROM analytics_real_events
            WHERE name = 'screen_viewed' AND properties->>'screen' = 'welcome' AND anonymous_id IS NOT NULL
            GROUP BY 1
        ),
        clicked AS (SELECT DISTINCT anonymous_id FROM analytics_real_events WHERE name = 'register_clicked'),
        logged AS (
            SELECT DISTINCT anonymous_id, user_id FROM analytics_real_events
            WHERE name = 'login_handshake_completed' AND anonymous_id IS NOT NULL
        ),
        onboarded AS (SELECT DISTINCT user_id FROM analytics_real_events WHERE name = 'onboarding_completed'),
        first_item AS (
            SELECT DISTINCT user_id FROM analytics_real_events WHERE name IN ('task_created', 'event_created')
        )
        SELECT w.day,
               count(DISTINCT w.anonymous_id) AS welcome_viewed,
               count(DISTINCT c.anonymous_id) AS register_clicked,
               count(DISTINCT l.user_id) AS logged_in,
               count(DISTINCT o.user_id) AS onboarding_completed,
               count(DISTINCT f.user_id) AS first_item_created
        FROM welcome w
        LEFT JOIN clicked c USING (anonymous_id)
        LEFT JOIN logged l USING (anonymous_id)
        LEFT JOIN onboarded o ON o.user_id = l.user_id
        LEFT JOIN first_item f ON f.user_id = l.user_id
        GROUP BY 1
        """,
    ),
    (
        "metrics_invites",
        """
        SELECT day,
               count(*) FILTER (WHERE name = 'invite_created') AS invites_created,
               count(*) FILTER (WHERE name = 'invite_shared') AS invites_shared,
               count(*) FILTER (WHERE name = 'invite_opened') AS invites_opened,
               count(*) FILTER (WHERE name = 'invite_accepted') AS invites_accepted,
               count(*) FILTER (WHERE name = 'user_signed_up'
                                AND properties->>'acquisition_source' = 'invite') AS signups_via_invite,
               count(*) FILTER (WHERE name = 'user_signed_up'
                                AND properties->>'acquisition_source' <> 'invite') AS signups_other
        FROM analytics_real_events
        WHERE name IN ('invite_created', 'invite_shared', 'invite_opened', 'invite_accepted', 'user_signed_up')
        GROUP BY 1
        """,
    ),
    (
        "metrics_ai_quality",
        """
        SELECT day,
               count(*) FILTER (WHERE name = 'capture_received' AND properties->>'content_type' = 'text') AS captures,
               count(*) FILTER (WHERE name = 'capture_received'
                                AND properties->>'content_type' <> 'text') AS captures_unsupported,
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
               ) AS confirm_rate
        FROM analytics_real_events
        WHERE name IN ('capture_received', 'capture_failed', 'draft_action_created', 'draft_action_confirmed',
                       'draft_action_revised', 'draft_action_cancelled', 'draft_action_expired')
        GROUP BY 1
        """,
    ),
    (
        "metrics_llm_cost",
        f"""
        SELECT (l.occurred_at AT TIME ZONE {TZ})::date AS day,
               l.feature, l.provider, l.model,
               count(*) AS calls,
               count(*) FILTER (WHERE l.status <> 'ok') AS failed_calls,
               count(*) FILTER (WHERE l.cost_micros IS NULL) AS unpriced_calls,
               sum(l.input_tokens) AS input_tokens,
               sum(l.output_tokens) AS output_tokens,
               round(coalesce(sum(l.cost_micros), 0) / 1000000.0, 4) AS cost_rub,
               round(avg(l.latency_ms)) AS avg_latency_ms
        FROM llm_usage l
        LEFT JOIN users u ON u.id = l.user_id
        WHERE l.provider <> 'fake' AND l.feature <> 'eval' AND u.is_test IS NOT TRUE
        GROUP BY 1, 2, 3, 4
        """,
    ),
    (
        "metrics_cost_per_dau",
        """
        WITH cost AS (SELECT day, sum(cost_rub) AS cost_rub, sum(calls) AS calls FROM metrics_llm_cost GROUP BY 1)
        SELECT coalesce(a.day, c.day) AS day,
               coalesce(a.dau, 0) AS dau,
               coalesce(c.calls, 0) AS llm_calls,
               coalesce(c.cost_rub, 0) AS cost_rub,
               round(coalesce(c.cost_rub, 0) / nullif(a.dau, 0), 4) AS rub_per_dau,
               round(coalesce(c.cost_rub, 0) / nullif(a.active_families, 0), 4) AS rub_per_active_family
        FROM metrics_active_users a
        FULL JOIN cost c ON c.day = a.day
        """,
    ),
    (
        "metrics_retention",
        """
        WITH act AS (SELECT DISTINCT user_id, activity_date FROM analytics_real_activity),
        cohorts AS (SELECT user_id, min(activity_date) AS cohort FROM act GROUP BY 1)
        SELECT c.cohort AS day,
               count(*) AS users,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM act a WHERE a.user_id = c.user_id
                                              AND a.activity_date = c.cohort + 1)) AS d1,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM act a WHERE a.user_id = c.user_id
                                              AND a.activity_date = c.cohort + 7)) AS d7,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM act a WHERE a.user_id = c.user_id
                                              AND a.activity_date = c.cohort + 30)) AS d30
        FROM cohorts c
        GROUP BY 1
        """,
    ),
    (
        "metrics_activation",
        f"""
        -- ARCHITECTURE §9.7: a family is activated if within 7 days it has ≥2 members and ≥3 items.
        SELECT (f.created_at AT TIME ZONE {TZ})::date AS day,
               count(*) AS families,
               count(*) FILTER (WHERE m.members >= 2 AND i.items >= 3) AS activated
        FROM families f
        JOIN users u ON u.id = f.created_by AND NOT u.is_test
        CROSS JOIN LATERAL (
            SELECT count(*) AS members FROM members
            WHERE family_id = f.id AND created_at < f.created_at + interval '7 days'
        ) m
        CROSS JOIN LATERAL (
            SELECT (SELECT count(*) FROM tasks
                     WHERE family_id = f.id AND created_at < f.created_at + interval '7 days')
                 + (SELECT count(*) FROM events
                     WHERE family_id = f.id AND created_at < f.created_at + interval '7 days') AS items
        ) i
        GROUP BY 1
        """,
    ),
]


def upgrade() -> None:
    for name, sql in VIEWS:
        op.execute(f"CREATE VIEW {name} AS {sql}")


def downgrade() -> None:
    for name, _ in reversed(VIEWS):
        op.execute(f"DROP VIEW IF EXISTS {name}")
