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


class AkhtabootScraper:
    """Scraper for Akhtaboot.com (Jordan & wider MENA career portal)."""

    BASE_URL = "https://www.akhtaboot.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Akhtaboot search results for given keywords, filtering for jobs <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Referer": "https://www.akhtaboot.com/",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/en/jordan/jobs/search?keywords={encoded}"
            logger.info(f"Fetching Akhtaboot URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Akhtaboot returned status {resp.status_code} for {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                job_links = soup.find_all("a", href=lambda h: h and "/jobs/" in h and "search" not in h)

                for a in job_links:
                    full_title_text = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not href or not full_title_text:
                        continue

                    # Extract unique job ID from href: /en/jordan/jobs/amman/167629-...
                    id_match = re.search(r"/(\d+)-", href)
                    raw_id = id_match.group(1) if id_match else str(hash(href))
                    full_id = f"akhtaboot_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    # Parse title, company, location from link text: e.g. "Amman, JordanSales Representative – Chemical Products - Telegraph Store"
                    title = full_title_text
                    company = "Confidential"
                    location = "Jordan / MENA"

                    # Check for location prefix
                    loc_match = re.match(r"^([^a-z0-9]+,\s*[^a-z0-9]+|[a-zA-Z\s]+,\s*[a-zA-Z\s]+)", full_title_text)
                    if loc_match:
                        location = loc_match.group(1).strip()
                        title = full_title_text[len(location):].strip()

                    # Check for company suffix "- Company Name"
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        title = parts[0].strip()
                        company = parts[1].strip()

                    card = a.find_parent("div", class_=lambda c: c and ("card" in c or "item" in c or "job" in c or "panel" in c)) or a.parent.parent
                    card_text = card.get_text(separator=" | ", strip=True) if card else ""

                    date_match = re.search(r"(\d+\s*(?:day|week|month|hour)s?\s*ago|today|yesterday|منذ\s+[^\s|]+)", card_text, re.I)
                    date_str = date_match.group(1) if date_match else "Recent"

                    if not is_posted_within_last_month(date_str, max_days=30):
                        continue

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str,
                        description_snippet=card_text[:350],
                        url=job_url,
                        source="Akhtaboot",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Akhtaboot: {e}")

        return jobs
