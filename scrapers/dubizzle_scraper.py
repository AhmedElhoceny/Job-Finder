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


class DubizzleScraper:
    """Scraper for Dubizzle (UAE & Egypt local jobs and vacancies)."""

    BASE_URLS = [
        ("https://uae.dubizzle.com", "UAE"),
        ("https://www.dubizzle.com.eg", "Egypt"),
    ]

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Dubizzle for matching job vacancies across UAE and Egypt."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for base_url, country_name in self.BASE_URLS:
            for kw in keywords[:2]:
                encoded = urllib.parse.quote_plus(kw.strip())
                search_url = f"{base_url}/en/jobs/search/?q={encoded}"
                logger.info(f"Fetching Dubizzle ({country_name}) URL: {search_url}")

                try:
                    resp = requests.get(search_url, impersonate="chrome", headers=headers, timeout=12)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.find_all("a", href=lambda h: h and ("/jobs/" in h or "/ad/" in h) and "search" not in h)

                    for a in links:
                        title = a.get_text(strip=True)
                        href = a.get("href", "")
                        if not href or not title or len(title) < 4:
                            continue

                        job_url = f"{base_url}{href}" if href.startswith("/") else href

                        id_match = re.search(r"-(\d+)(?:\.html|/|$)", href)
                        raw_id = id_match.group(1) if id_match else str(hash(job_url))
                        full_id = f"dubizzle_{raw_id}"

                        if full_id in self.seen_job_ids:
                            continue
                        self.seen_job_ids.add(full_id)

                        card = a.find_parent("div", class_=lambda c: c and ("card" in c or "item" in c or "listing" in c)) or a.parent.parent
                        card_text = card.get_text(separator=" | ", strip=True) if card else ""

                        date_match = re.search(r"(\d+\s*(?:day|week|month|hour)s?\s*ago|today|yesterday|منذ\s+[^\s|]+)", card_text, re.I)
                        date_str = date_match.group(1) if date_match else "Recent"

                        if not is_posted_within_last_month(date_str, max_days=30):
                            continue

                        job = ScrapedJob(
                            id=full_id,
                            title=title,
                            company="Dubizzle Employer",
                            location=f"{country_name} / Local",
                            date_posted=date_str,
                            description_snippet=card_text[:350],
                            url=job_url,
                            source=f"Dubizzle ({country_name})",
                            matched_keyword=kw,
                        )
                        jobs.append(job)

                        if len(jobs) >= max_jobs:
                            break

                    time.sleep(self.request_delay)

                except Exception as e:
                    logger.error(f"Error scraping Dubizzle ({country_name}): {e}")

        return jobs
