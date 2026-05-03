import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path("research_history.db")


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                status TEXT NOT NULL,
                search_results TEXT NOT NULL DEFAULT '',
                sources_json TEXT NOT NULL DEFAULT '[]',
                report TEXT NOT NULL DEFAULT '',
                feedback TEXT NOT NULL DEFAULT '',
                error TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                run_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_job_steps (
                job_id INTEGER NOT NULL,
                step TEXT NOT NULL,
                status TEXT NOT NULL,
                field TEXT,
                value TEXT NOT NULL DEFAULT '',
                error TEXT,
                started_at TEXT,
                completed_at TEXT,
                PRIMARY KEY (job_id, step)
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(research_runs)").fetchall()
        }
        if "structured_report_json" not in columns:
            connection.execute(
                "ALTER TABLE research_runs ADD COLUMN structured_report_json TEXT NOT NULL DEFAULT '{}'"
            )


def save_research_run(topic: str, state: dict[str, Any], status: str = "completed") -> int:
    init_db()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO research_runs (
                topic,
                status,
                search_results,
                sources_json,
                report,
                feedback,
                structured_report_json,
                error,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                topic,
                status,
                str(state.get("search_results", "")),
                json.dumps(state.get("sources", []), ensure_ascii=False),
                str(state.get("report", "")),
                str(state.get("feedback", "")),
                json.dumps(state.get("structured_report", {}), ensure_ascii=False),
                state.get("error"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return int(cursor.lastrowid)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["sources"] = json.loads(item.pop("sources_json") or "[]")
    item["structured_report"] = json.loads(item.pop("structured_report_json", "{}") or "{}")
    return item


def list_research_runs(limit: int = 20) -> list[dict[str, Any]]:
    init_db()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, topic, status, sources_json, structured_report_json, report, feedback, error, created_at
            FROM research_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [row_to_dict(row) for row in rows]


def get_research_run(run_id: int) -> dict[str, Any] | None:
    init_db()

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM research_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()

    return row_to_dict(row) if row else None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_research_job(topic: str) -> int:
    init_db()
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO research_jobs (topic, status, created_at, updated_at)
            VALUES (?, 'pending', ?, ?)
            """,
            (topic, timestamp, timestamp),
        )
        return int(cursor.lastrowid)


def update_research_job(
    job_id: int,
    status: str,
    error: str | None = None,
    run_id: int | None = None,
) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE research_jobs
            SET status = ?, error = COALESCE(?, error), run_id = COALESCE(?, run_id), updated_at = ?
            WHERE id = ?
            """,
            (status, error, run_id, now_iso(), job_id),
        )


def upsert_job_step(
    job_id: int,
    step: str,
    status: str,
    field: str | None = None,
    value: str = "",
    error: str | None = None,
) -> None:
    init_db()
    timestamp = now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO research_job_steps (
                job_id, step, status, field, value, error, started_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, step) DO UPDATE SET
                status = excluded.status,
                field = COALESCE(excluded.field, research_job_steps.field),
                value = excluded.value,
                error = excluded.error,
                started_at = COALESCE(research_job_steps.started_at, excluded.started_at),
                completed_at = excluded.completed_at
            """,
            (
                job_id,
                step,
                status,
                field,
                value,
                error,
                timestamp,
                timestamp if status in {"completed", "failed"} else None,
            ),
        )


def get_research_job(job_id: int) -> dict[str, Any] | None:
    init_db()
    with get_connection() as connection:
        job = connection.execute(
            "SELECT * FROM research_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not job:
            return None
        steps = connection.execute(
            """
            SELECT step, status, field, value, error, started_at, completed_at
            FROM research_job_steps
            WHERE job_id = ?
            ORDER BY started_at
            """,
            (job_id,),
        ).fetchall()

    item = dict(job)
    item["steps"] = [dict(step) for step in steps]
    return item
