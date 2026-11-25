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


class NaukrigulfScraper:
    """Scraper for Naukrigulf.com (Leading job portal across UAE, Saudi Arabia, and GCC)."""

    BASE_URL = "https://www.naukrigulf.com"

    def __init__(self, request_delay: float = 1.5):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    @staticmethod
    def keyword_to_slug(keyword: str) -> str:
        cleaned = keyword.strip().lower()
        cleaned = re.sub(r"\b(senior|lead|remote|junior|fresher|staff)\b", "", cleaned).strip()
        slug = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
        return slug or "software-engineer"

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Naukrigulf for given keywords/roles across GCC countries."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.naukrigulf.com/",
            "client-type": "desktop",
            "systemId": "1112",
        }

        tested_slugs: set[str] = set()

        for kw in keywords[:3]:
            slug = self.keyword_to_slug(kw)
            if slug in tested_slugs:
                continue
            tested_slugs.add(slug)

            search_url = f"{self.BASE_URL}/{slug}-jobs"
            logger.info(f"Fetching Naukrigulf URL: {search_url}")

            try:
                resp = requests.get(search_url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Naukrigulf returned status {resp.status_code} for {search_url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                # Look for job links or articles
                job_links = soup.find_all("a", href=lambda h: h and ("-jobs-" in h or "/job-listings-" in h))

                for a in job_links:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not href or not title:
                        continue

                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    id_match = re.search(r"-(\d+)(?:\.html|/|$)", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"naukrigulf_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    card = a.find_parent("article") or a.find_parent("div", class_=lambda c: c and ("card" in c or "tuple" in c or "job" in c)) or a.parent.parent
                    card_text = card.get_text(separator=" | ", strip=True) if card else ""

                    date_match = re.search(r"(\d+\s*(?:day|week|month|hour)s?\s*ago|today|yesterday|\d{1,2}\s+[a-zA-Z]{3,9})", card_text, re.I)
                    date_str = date_match.group(1) if date_match else "Recent"

                    if not is_posted_within_last_month(date_str, max_days=30):
                        continue

                    parts = [p.strip() for p in card_text.split("|") if p.strip()]
                    company = parts[1] if len(parts) > 1 and parts[1] != title else "Confidential (GCC)"
                    location = parts[2] if len(parts) > 2 else "UAE / Saudi Arabia / GCC"

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str,
                        description_snippet=card_text[:350],
                        url=job_url,
                        source="Naukrigulf",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Naukrigulf: {e}")

        return jobs
