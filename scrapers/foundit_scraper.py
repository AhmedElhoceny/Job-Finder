from datetime import datetime
import logging
import time
import urllib.parse
from typing import Optional
from curl_cffi import requests

from core.models.job import ScrapedJob
from core.utils.date_parser import is_posted_within_last_month

logger = logging.getLogger(__name__)


class FounditScraper:
    """Scraper for Foundit.in (formerly Monster India — India, UAE, Singapore, Philippines)."""

    BASE_URL = "https://www.foundit.in"
    API_URL = "https://www.foundit.in/middleware/jobsearch"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Queries Foundit middleware API for vacancies, strictly filtering for postings <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "application/json",
            "Referer": "https://www.foundit.in/srp/results",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.API_URL}?query={encoded}&limit=15"
            logger.info(f"Fetching Foundit API: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=12)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                results = data.get("jobSearchResponse", {}).get("data", [])

                for item in results:
                    job_id = item.get("jobId")
                    if not job_id:
                        continue
                    full_id = f"foundit_{job_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    title = item.get("title") or "Software Engineer"
                    company = item.get("companyName") or item.get("company", {}).get("name") or "Confidential"

                    # Location
                    loc_items = item.get("locations", [])
                    city_names = [l.get("city") for l in loc_items if isinstance(l, dict) and l.get("city")]
                    location = ", ".join(city_names) if city_names else "India / Remote"

                    # Date parsing (createdAt is unix timestamp in ms)
                    created_at_ms = item.get("createdAt")
                    date_str = "Recent"
                    if created_at_ms:
                        try:
                            created_dt = datetime.fromtimestamp(created_at_ms / 1000.0)
                            delta_days = (datetime(2026, 11, 24) - created_dt).days
                            date_str = f"{delta_days} days ago" if delta_days > 0 else "Today"

                            # === Date Range Filter: Exclude jobs older than 30 days ===
                            if delta_days > 30:
                                continue
                        except Exception:
                            pass

                    job_url = item.get("redirectUrl") or f"{self.BASE_URL}/job/{job_id}"

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str,
                        description_snippet=item.get("description", "")[:350],
                        url=job_url,
                        source="Foundit (India/APAC)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error querying Foundit: {e}")

        return jobs
