import logging
import re
import time
from typing import Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

from core.models.job import ScrapedJob
from core.utils.date_parser import is_posted_within_last_month

logger = logging.getLogger(__name__)


class KalibrrScraper:
    """Scraper for Kalibrr.com (Southeast Asia: Philippines, Indonesia, Remote)."""

    BASE_URL = "https://www.kalibrr.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    @staticmethod
    def keyword_to_slug(keyword: str) -> str:
        cleaned = keyword.strip().lower()
        cleaned = re.sub(r"\b(senior|lead|remote|junior|fresher|staff)\b", "", cleaned).strip()
        slug = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
        return slug or "python"

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Kalibrr for vacancies matching keywords, strictly filtering for postings <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.kalibrr.com/",
        }

        for kw in keywords[:3]:
            slug = self.keyword_to_slug(kw)
            url = f"{self.BASE_URL}/job-board/te/{slug}"
            logger.info(f"Fetching Kalibrr URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=12)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=lambda h: h and "/c/" in h and "/jobs/" in h and len(h) > 25)

                for a in links:
                    title = a.get_text(strip=True)
                    if not title or title.lower() in ("view post", "apply"):
                        continue

                    href = a.get("href", "")
                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    # Extract ID
                    id_match = re.search(r"/jobs/(\d+)/", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"kalibrr_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    card = (
                        a.find_parent("div", class_=lambda c: c and ("card" in c or "item" in c or "grid" in c))
                        or a.parent.parent.parent
                    )
                    card_text = card.get_text(separator=" | ", strip=True) if card else ""

                    # Extract hiring date (e.g. 'Recruiter was hiring 6 hours ago', '2 days ago')
                    date_match = re.search(r"(\d+\s*(?:hour|day|week|month)s?\s*ago|today|yesterday)", card_text, re.I)
                    date_str = date_match.group(1) if date_match else None

                    # === Date Range Filter: Exclude jobs older than 1 month ===
                    if date_str and not is_posted_within_last_month(date_str, max_days=30):
                        logger.debug(f"Skipping Kalibrr job '{title}' - older than 1 month ({date_str})")
                        continue

                    # Extract company and location from card text
                    parts = [p.strip() for p in card_text.split("|") if p.strip()]
                    company = parts[1] if len(parts) > 1 and parts[1] != title else "Tech Company"
                    location = parts[2] if len(parts) > 2 else "Philippines / Remote"

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str or "Recent",
                        description_snippet=card_text[:350],
                        url=job_url,
                        source="Kalibrr (Southeast Asia)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Kalibrr: {e}")

        return jobs
