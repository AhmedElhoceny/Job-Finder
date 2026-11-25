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


class WuzzufScraper:
    """Scraper for Wuzzuf.net (Egypt's #1 Job Board for tech & software roles)."""

    BASE_URL = "https://wuzzuf.net"

    def __init__(self, request_delay: float = 1.5):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keyword(self, keyword: str, max_pages: int = 2) -> list[ScrapedJob]:
        """Scrapes Wuzzuf search results for a given keyword across pages,

        strictly filtering for jobs posted within the last 30 days.
        """
        jobs: list[ScrapedJob] = []
        encoded_kw = urllib.parse.quote_plus(keyword.strip())

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Referer": "https://wuzzuf.net/",
        }

        for page in range(max_pages):
            search_url = f"{self.BASE_URL}/search/jobs/?a=hpb&q={encoded_kw}&start={page}"
            logger.info(f"Fetching Wuzzuf URL: {search_url}")

            try:
                resp = requests.get(search_url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Wuzzuf returned {resp.status_code} for {search_url}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                job_links = soup.find_all("a", href=lambda h: h and "/jobs/p/" in h)

                if not job_links:
                    break

                page_new_jobs = 0

                for a in job_links:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not href or not title:
                        continue
                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    # Extract unique job ID
                    id_match = re.search(r"/jobs/p/([a-zA-Z0-9]+)-", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"wuzzuf_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    # Locate parent job card container
                    card = (
                        a.find_parent("div", class_=lambda c: c and "css-1gatmva" in c)
                        or a.find_parent("div", class_=lambda c: c and "css-pkv5jc" in c)
                        or a.parent.parent.parent
                    )
                    card_text = card.get_text(separator=" | ", strip=True) if card else ""

                    # Extract company name
                    comp_el = (
                        card.find("a", href=lambda h: h and "/jobs/careers/" in h)
                        or card.find("a", class_=lambda c: c and "css-12e27e8" in c)
                    ) if card else None
                    company = comp_el.get_text(strip=True).rstrip(" -") if comp_el else "Confidential"

                    # Extract location
                    loc_el = card.find("span", class_=lambda c: c and "css-5wys0k" in c) if card else None
                    location = loc_el.get_text(strip=True) if loc_el else "Cairo, Egypt"

                    # Extract Date Posted
                    date_el = (
                        card.find("div", class_=lambda c: c and ("css-do2t5v" in c or "css-152e90k" in c))
                    ) if card else None
                    date_str = date_el.get_text(strip=True) if date_el else ""
                    if not date_str:
                        # Fallback regex search on card text
                        m = re.search(r"(\d+\s*(?:day|month|hour|week|minute)s?\s*ago|today|yesterday)", card_text, re.I)
                        date_str = m.group(1) if m else "Recent"

                    # === Date Range Filter: Exclude jobs posted older than 1 month ===
                    if not is_posted_within_last_month(date_str, max_days=30):
                        logger.debug(f"Skipping Wuzzuf job '{title}' - posted older than 1 month ({date_str})")
                        continue

                    # Extract career level / skills snippet
                    desc = card_text.replace(title, "").replace(company, "").strip(" | ")

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str,
                        description_snippet=desc[:500],
                        url=job_url,
                        source="Wuzzuf",
                        matched_keyword=keyword,
                    )
                    jobs.append(job)
                    page_new_jobs += 1

                if page_new_jobs == 0:
                    break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Wuzzuf ({search_url}): {e}")
                break

        return jobs
