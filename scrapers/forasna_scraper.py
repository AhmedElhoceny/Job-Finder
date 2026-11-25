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


class ForasnaScraper:
    """Scraper for Forasna.com (Egypt's major platform for technical, operational, and entry/mid roles)."""

    BASE_URL = "https://forasna.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Forasna search results for keywords, strictly filtering jobs posted <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Referer": "https://forasna.com/",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/job/search?q={encoded}"
            logger.info(f"Fetching Forasna URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Forasna returned status {resp.status_code} for {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                job_links = soup.find_all("a", href=lambda h: h and "/job/p/" in h)

                for a in job_links:
                    title = a.get_text(strip=True)
                    if not title:
                        continue

                    href = a.get("href", "")
                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    id_match = re.search(r"-(\d+)$", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"forasna_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    card = a.find_parent("div", class_=lambda c: c and ("card" in c or "item" in c or "job" in c)) or a.parent.parent
                    card_text = card.get_text(separator=" | ", strip=True) if card else ""

                    date_match = re.search(r"(منذ\s+[^\s|]+(?:\s+[^\s|]+)?|\d+\s*days?\s*ago|today|yesterday|جديدة)", card_text, re.I)
                    date_str = date_match.group(1) if date_match else "Recent"

                    if not is_posted_within_last_month(date_str, max_days=30):
                        continue

                    # Extract company and location from URL path or card text
                    # URL usually: /job/p/title-company-country-city-id
                    url_parts = href.split("/")[-1].split("-")
                    location = "Egypt"
                    company = "Confidential"
                    if len(url_parts) >= 4:
                        company = urllib.parse.unquote(url_parts[-4])
                        location = f"{urllib.parse.unquote(url_parts[-3])}, Egypt"

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str,
                        description_snippet=card_text[:350],
                        url=job_url,
                        source="Forasna",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Forasna: {e}")

        return jobs
