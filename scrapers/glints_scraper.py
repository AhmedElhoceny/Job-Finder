import json
import logging
import re
import time
import urllib.parse
from typing import Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

from core.models.job import ScrapedJob
from core.utils.date_parser import is_posted_within_last_month

logger = logging.getLogger(__name__)


class GlintsScraper:
    """Scraper for Glints.com (Southeast Asia's leading tech talent ecosystem - Singapore, Indonesia, Vietnam, Taiwan)."""

    BASE_URL = "https://glints.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Glints for matching vacancies, extracting rich structured entities via Next.js hydration payload."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://glints.com/",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/sg/opportunities/jobs/explore?keyword={encoded}"
            logger.info(f"Fetching Glints URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Glints returned status {resp.status_code} for {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                next_tag = soup.find("script", id="__NEXT_DATA__")

                if next_tag and next_tag.string:
                    try:
                        data = json.loads(next_tag.string)
                        init_jobs = data.get("props", {}).get("pageProps", {}).get("initialJobs", {})
                        job_list = init_jobs.get("jobsInPage", []) if isinstance(init_jobs, dict) else []

                        for item in job_list:
                            job_id = str(item.get("id") or "")
                            if not job_id:
                                continue
                            full_id = f"glints_{job_id}"

                            if full_id in self.seen_job_ids:
                                continue
                            self.seen_job_ids.add(full_id)

                            title = item.get("title") or "Software Engineer"
                            comp_obj = item.get("company") or {}
                            company = comp_obj.get("name") if isinstance(comp_obj, dict) else "Confidential"

                            work_option = item.get("workArrangementOption") or "Remote/Hybrid"
                            city = item.get("city") or "Singapore / Southeast Asia"
                            location = f"{city} ({work_option})" if work_option else str(city)

                            # Date parsing
                            created_at = item.get("createdAt") or item.get("updatedAt") or ""
                            date_str = created_at[:10] if created_at else "Recent"

                            if created_at and not is_posted_within_last_month(created_at[:10], max_days=30):
                                continue

                            job_url = f"{self.BASE_URL}/sg/opportunities/jobs/{job_id}"

                            job = ScrapedJob(
                                id=full_id,
                                title=title,
                                company=company,
                                location=location,
                                date_posted=date_str,
                                description_snippet=f"Arrangement: {work_option} | Status: {item.get('status')}",
                                url=job_url,
                                source="Glints (Southeast Asia)",
                                matched_keyword=kw,
                            )
                            jobs.append(job)

                            if len(jobs) >= max_jobs:
                                break

                    except Exception as err:
                        logger.warning(f"Failed parsing Glints __NEXT_DATA__: {err}")

                # Fallback to HTML cards if Next.js data was not available
                if not jobs:
                    cards = soup.select("[class*='JobCard']") or soup.find_all("a", href=lambda h: h and "/opportunities/jobs/" in h)
                    for a in cards:
                        title = a.get_text(strip=True)
                        href = a.get("href", "")
                        if not title or not href:
                            continue
                        job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                        full_id = f"glints_{hash(job_url)}"
                        if full_id in self.seen_job_ids:
                            continue
                        self.seen_job_ids.add(full_id)
                        jobs.append(
                            ScrapedJob(
                                id=full_id,
                                title=title,
                                company="Glints Employer",
                                location="Singapore / Southeast Asia",
                                date_posted="Recent",
                                description_snippet="",
                                url=job_url,
                                source="Glints (Southeast Asia)",
                                matched_keyword=kw,
                            )
                        )
                        if len(jobs) >= max_jobs:
                            break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Glints: {e}")

        return jobs
