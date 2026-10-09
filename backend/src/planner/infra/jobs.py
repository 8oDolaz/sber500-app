"""Procrastinate (Postgres-based jobs, ARCHITECTURE §10). Tasks live in entrypoints/worker/tasks.py."""

import procrastinate

from planner.settings import get_settings

job_app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=get_settings().sync_database_url),
    import_paths=["planner.entrypoints.worker.tasks"],
)
