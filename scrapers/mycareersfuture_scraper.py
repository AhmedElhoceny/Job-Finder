import logging
import urllib.parse
from typing import Optional
from curl_cffi import requests

from core.models.job import ScrapedJob
from core.utils.date_parser import is_posted_within_last_month

logger = logging.getLogger(__name__)


class MyCareersFutureScraper:
    """Scraper for MyCareersFuture (Singapore's official national job portal)."""

    BASE_API_URL = "https://api.mycareersfuture.gov.sg/v2/jobs"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Queries MyCareersFuture API for given keywords, filtering strictly for postings <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_API_URL}?search={encoded}&limit=15"
            logger.info(f"Fetching MyCareersFuture API: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=12)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                results = data.get("results", [])

                for item in results:
                    uuid = item.get("uuid")
                    if not uuid:
                        continue
                    full_id = f"mcf_{uuid}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    title = item.get("title") or "Software Engineer"
                    company_obj = item.get("postedCompany") or {}
                    company = company_obj.get("name") or "Confidential"

                    meta = item.get("metadata") or {}
                    date_posted = meta.get("originalPostingDate") or meta.get("lastUpdatedDate") or meta.get("expiryDate")

                    # === Date Range Filter: Exclude jobs older than 1 month ===
                    if date_posted and not is_posted_within_last_month(date_posted, max_days=30):
                        continue

                    # Description snippet
                    desc_obj = item.get("description") or ""
                    clean_desc = desc_obj.replace("<p>", "").replace("</p>", " ")[:350]

                    job_url = f"https://www.mycareersfuture.gov.sg/job/{uuid}"

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location="Singapore",
                        date_posted=date_posted or "Recent",
                        description_snippet=clean_desc,
                        url=job_url,
                        source="MyCareersFuture (Singapore)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

            except Exception as e:
                logger.error(f"Error querying MyCareersFuture: {e}")

        return jobs
