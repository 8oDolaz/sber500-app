"""Import every SQLAlchemy model so Base.metadata is complete (Alembic, tests)."""


def import_all_models() -> None:
    import planner.infra.outbox
    import planner.modules.analytics.tables
    import planner.modules.assistant.tables
    import planner.modules.families.tables
    import planner.modules.identity.tables
    import planner.modules.notifications.tables
    import planner.modules.planning.tables  # noqa: F401
