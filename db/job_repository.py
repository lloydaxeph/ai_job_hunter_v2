from __future__ import annotations

from datetime import datetime
from pathlib import Path
from sqlite3 import Connection, Cursor

import pandas as pd

from core.job import Job


class JobRepository:
    """SQLite-backed repository for `Job` records.

    All statement execution funnels through `_execute`/`_execute_write` so
    each public method is a single call instead of hand-rolled
    cursor/execute/commit boilerplate.
    """

    def __init__(self, connection: Connection):
        self.connection = connection

    def _execute(self, query: str, params: tuple = ()) -> Cursor:
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        return cursor

    def _execute_write(self, query: str, params: tuple = ()) -> Cursor:
        cursor = self._execute(query, params)
        self.connection.commit()
        return cursor

    def save(self, job: Job) -> bool:
        cursor = self._execute_write(
            """
            INSERT OR IGNORE INTO jobs (
                job_id, job_title, company, url, site, score,
                description, resume_used, date, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id,
                job.title,
                job.company,
                job.url,
                job.site,
                job.score,
                job.description,
                job.resume_used,
                job.date.isoformat(),
                str(job.status),
            ),
        )
        return cursor.rowcount == 1

    def exists(self, job_id: str) -> bool:
        cursor = self._execute(
            "SELECT 1 FROM jobs WHERE job_id = ? LIMIT 1", (job_id,)
        )
        return cursor.fetchone() is not None

    def get(self, job_id: str) -> Job | None:
        cursor = self._execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        return self._row_to_job(row) if row else None

    def get_all(self) -> list[Job]:
        cursor = self._execute("SELECT * FROM jobs ORDER BY date DESC")
        return [self._row_to_job(row) for row in cursor.fetchall()]

    def get_jobs_by_status(self, status: str) -> list[Job]:
        cursor = self._execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY date DESC", (status,)
        )
        return [self._row_to_job(row) for row in cursor.fetchall()]

    def find_scored_duplicate(self, company: str, title: str) -> Job | None:
        """Find a previously-scored job at the same company with the same title.

        Used to skip a redundant LLM scoring call for repost-style duplicates
        that were filtered out of exact job_id dedup (e.g. re-scraped after a
        listing refresh with a new URL).
        """
        cursor = self._execute(
            """
            SELECT * FROM jobs
            WHERE company = ? AND job_title = ? AND score > 0
            ORDER BY date DESC
            LIMIT 1
            """,
            (company, title),
        )
        row = cursor.fetchone()
        return self._row_to_job(row) if row else None

    def delete(self, job_id: str) -> None:
        self._execute_write("DELETE FROM jobs WHERE job_id = ?", (job_id,))

    def update_description(self, job_id: str, description: str) -> None:
        self._execute_write(
            "UPDATE jobs SET description = ? WHERE job_id = ?", (description, job_id)
        )

    def update_status(self, job_id: str, status: str) -> None:
        self._execute_write(
            "UPDATE jobs SET status = ? WHERE job_id = ?", (str(status), job_id)
        )

    def update_score(self, job_id: str, score: int) -> None:
        self._execute_write(
            "UPDATE jobs SET score = ? WHERE job_id = ?", (score, job_id)
        )

    def update_resume_used(self, job_id: str, resume_used: str) -> None:
        self._execute_write(
            "UPDATE jobs SET resume_used = ? WHERE job_id = ?", (resume_used, job_id)
        )

    def to_csv(self, output_path: str = "Data/applications.csv") -> None:
        cursor = self._execute(
            """
            SELECT job_id, job_title, company, url, site, score,
                   description, resume_used, date, status
            FROM jobs
            ORDER BY date DESC
            """
        )
        rows = cursor.fetchall()

        if not rows:
            print("No jobs found.")
            return

        df = pd.DataFrame([dict(row) for row in rows])

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output, index=False)

        print(f"Exported {len(df)} jobs to {output}")

    @staticmethod
    def _row_to_job(row) -> Job:
        return Job(
            title=row["job_title"],
            company=row["company"],
            url=row["url"],
            site=row["site"],
            score=row["score"],
            description=row["description"],
            resume_used=row["resume_used"],
            date=datetime.fromisoformat(row["date"]),
            status=row["status"],
        )
