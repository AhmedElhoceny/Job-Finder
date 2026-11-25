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


class JobsDBScraper:
    """Scraper for JobsDB.com (Premier job portal for Hong Kong, Thailand, and East/Southeast Asia)."""

    COUNTRY_DOMAINS = [
        ("https://hk.jobsdb.com", "Hong Kong"),
        ("https://th.jobsdb.com", "Thailand"),
    ]

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes JobsDB across regional portals for matching vacancies."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://hk.jobsdb.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for base_url, country in self.COUNTRY_DOMAINS:
            for kw in keywords[:2]:
                encoded = urllib.parse.quote_plus(kw.strip())
                search_url = f"{base_url}/jobs?keywords={encoded}"
                logger.info(f"Fetching JobsDB ({country}) URL: {search_url}")

                try:
                    resp = requests.get(search_url, impersonate="chrome", headers=headers, timeout=12)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.find_all("a", href=lambda h: h and ("/job/" in h or "/jobs/" in h) and "keywords=" not in h)

                    for a in links:
                        title = a.get_text(strip=True)
                        href = a.get("href", "")
                        if not href or not title or len(title) < 4:
                            continue

                        job_url = f"{base_url}{href}" if href.startswith("/") else href

                        id_match = re.search(r"/job/(\d+)", href) or re.search(r"-(\d+)(?:\?|$)", href)
                        raw_id = id_match.group(1) if id_match else str(hash(job_url))
                        full_id = f"jobsdb_{raw_id}"

                        if full_id in self.seen_job_ids:
                            continue
                        self.seen_job_ids.add(full_id)

                        card = a.find_parent("article") or a.find_parent("div", class_=lambda c: c and ("card" in c or "item" in c or "job" in c)) or a.parent.parent
                        card_text = card.get_text(separator=" | ", strip=True) if card else ""

                        date_match = re.search(r"(\d+\s*(?:day|week|month|hour)s?\s*ago|today|yesterday|\d{1,2}\s+[a-zA-Z]{3,9})", card_text, re.I)
                        date_str = date_match.group(1) if date_match else "Recent"

                        if not is_posted_within_last_month(date_str, max_days=30):
                            continue

                        parts = [p.strip() for p in card_text.split("|") if p.strip()]
                        company = parts[1] if len(parts) > 1 and parts[1] != title else "Asian Tech Employer"
                        location = f"{country} / Remote"

                        job = ScrapedJob(
                            id=full_id,
                            title=title,
                            company=company,
                            location=location,
                            date_posted=date_str,
                            description_snippet=card_text[:350],
                            url=job_url,
                            source=f"JobsDB ({country})",
                            matched_keyword=kw,
                        )
                        jobs.append(job)

                        if len(jobs) >= max_jobs:
                            break

                    time.sleep(self.request_delay)

                except Exception as e:
                    logger.error(f"Error scraping JobsDB ({country}): {e}")

        return jobs
