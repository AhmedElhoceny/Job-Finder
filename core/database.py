import sqlite3
from pathlib import Path
from typing import Any, Optional

from config.settings import get_settings
from core.models.job import ScrapedJob


class JobDatabase:
    """Manages SQLite storage and deduplication for scraped jobs."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_settings().absolute_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates the jobs table if it does not exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT,
                    location TEXT,
                    career_level TEXT,
                    date_posted TEXT,
                    description_snippet TEXT,
                    url TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL,
                    matched_keyword TEXT,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'DISCOVERED'
                )
                """
            )
            conn.commit()

    def save_jobs(self, jobs: list[ScrapedJob]) -> int:
        """Inserts new jobs into the database; ignores existing duplicates by ID or URL."""
        new_count = 0
        with self._get_connection() as conn:
            for job in jobs:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs (
                        id, title, company, location, career_level,
                        date_posted, description_snippet, url, source, matched_keyword
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.id,
                        job.title,
                        job.company,
                        job.location,
                        job.career_level,
                        job.date_posted,
                        job.description_snippet,
                        job.url,
                        job.source,
                        job.matched_keyword,
                    ),
                )
                if cursor.rowcount > 0:
                    new_count += 1
            conn.commit()
        return new_count

    def get_all_jobs(self, source: Optional[str] = None) -> list[dict[str, Any]]:
        """Retrieves all jobs stored in the database."""
        with self._get_connection() as conn:
            if source:
                cursor = conn.execute("SELECT * FROM jobs WHERE source = ? ORDER BY scraped_at DESC", (source,))
            else:
                cursor = conn.execute("SELECT * FROM jobs ORDER BY scraped_at DESC")
            return [dict(row) for row in cursor.fetchall()]
