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


class TanqeebScraper:
    """Scraper for Tanqeeb.com (Major MENA job aggregator for Egypt, Saudi Arabia, UAE, and GCC)."""

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(
        self,
        keywords: list[str],
        countries: list[str] = ["egypt", "saudi", "uae"],
        max_jobs_per_query: int = 10,
    ) -> list[ScrapedJob]:
        """Queries Tanqeeb across target countries and keywords, strictly filtering jobs <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Referer": "https://www.tanqeeb.com/",
        }

        for country in countries[:2]:  # Limit country queries for speed
            for kw in keywords[:2]:
                encoded_kw = urllib.parse.quote_plus(kw.strip())
                url = f"https://{country}.tanqeeb.com/jobs/search?keywords={encoded_kw}"
                logger.info(f"Fetching Tanqeeb URL: {url}")

                try:
                    resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    headers_tags = soup.find_all(["h2", "h3"])

                    for h in headers_tags:
                        a = h.find("a")
                        if not a:
                            continue
                        title = a.get_text(strip=True)
                        href = a.get("href", "")
                        if not href or len(href) < 15 or "search" in href or "change_lang" in href:
                            continue

                        job_url = f"https://{country}.tanqeeb.com{href}" if href.startswith("/") else href

                        # Extract unique ID
                        id_match = re.search(r"/(\d+)\.html", href)
                        raw_id = id_match.group(1) if id_match else str(hash(job_url))
                        full_id = f"tanqeeb_{raw_id}"

                        if full_id in self.seen_job_ids:
                            continue
                        self.seen_job_ids.add(full_id)

                        card = (
                            h.find_parent("div", class_=lambda c: c and ("card" in c or "item" in c or "job" in c))
                            or h.parent.parent
                        )
                        card_text = card.get_text(separator=" | ", strip=True) if card else ""

                        # Extract Date (e.g. '3 September 2026', 'منذ 3 أيام', '17 Nov')
                        date_match = re.search(
                            r"(\d{1,2}\s+[a-zA-Z\u0621-\u064A]+\s*\d{0,4}|منذ\s+[^\s|]+(?:\s+[^\s|]+)?|\d+\s*days?\s*ago|today|yesterday)",
                            card_text,
                            re.I,
                        )
                        date_str = date_match.group(1) if date_match else None

                        # === Date Range Filter: Exclude jobs posted older than 1 month ===
                        if date_str and not is_posted_within_last_month(date_str, max_days=30):
                            logger.debug(f"Skipping Tanqeeb job '{title}' - older than 1 month ({date_str})")
                            continue

                        # Extract company/location from card text
                        parts = [p.strip() for p in card_text.split("|") if p.strip()]
                        company = "Confidential"
                        location = f"{country.capitalize()} / MENA"
                        for p in parts:
                            if any(c in p.lower() for c in ["cairo", "dubai", "riyadh", "egypt", "saudi", "uae", "remote"]):
                                location = p
                                break

                        job = ScrapedJob(
                            id=full_id,
                            title=title,
                            company=company,
                            location=location,
                            date_posted=date_str or "Recent",
                            description_snippet=card_text[:300],
                            url=job_url,
                            source="Tanqeeb",
                            matched_keyword=kw,
                        )
                        jobs.append(job)

                        if len(jobs) >= max_jobs_per_query:
                            break

                    time.sleep(self.request_delay)

                except Exception as e:
                    logger.error(f"Error scraping Tanqeeb ({url}): {e}")

        return jobs
