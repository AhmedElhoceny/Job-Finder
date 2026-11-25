import logging
import re
import time
from typing import Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

from core.models.job import ScrapedJob
from core.utils.date_parser import is_posted_within_last_month

logger = logging.getLogger(__name__)


class InternshalaScraper:
    """Scraper for Internshala.com (India tech, engineering, and software jobs)."""

    BASE_URL = "https://internshala.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    @staticmethod
    def keyword_to_slug(keyword: str) -> str:
        cleaned = keyword.strip().lower()
        if "backend" in cleaned:
            return "backend-development"
        if "software" in cleaned:
            return "software-development"
        if "python" in cleaned:
            return "python"
        if "full" in cleaned:
            return "full-stack-development"
        return "software-development"

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Internshala for vacancies matching keywords, strictly filtering for postings <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://internshala.com/",
        }

        tested_slugs: set[str] = set()

        for kw in keywords[:3]:
            slug = self.keyword_to_slug(kw)
            if slug in tested_slugs:
                continue
            tested_slugs.add(slug)

            url = f"{self.BASE_URL}/jobs/{slug}-jobs/"
            logger.info(f"Fetching Internshala URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=12)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select(".individual_internship")

                for card in cards:
                    title_tag = card.find("h3") or card.find("a", class_=lambda c: c and "job-title" in c)
                    if not title_tag:
                        continue
                    title = title_tag.get_text(strip=True)

                    link_tag = card.find("a", href=lambda h: h and "/job/detail/" in h)
                    href = link_tag.get("href", "") if link_tag else ""
                    if not href:
                        continue
                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    # Extract ID
                    id_match = re.search(r"/detail/.*?-(\d+)", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"internshala_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    comp_tag = card.find("p", class_=lambda c: c and "company-name" in c)
                    company = comp_tag.get_text(strip=True) if comp_tag else "Confidential"

                    loc_tag = card.find("a", class_=lambda c: c and "location" in c)
                    location = loc_tag.get_text(strip=True) if loc_tag else "India / Remote"

                    card_text = card.get_text(separator=" | ", strip=True)

                    # Extract date
                    date_match = re.search(r"(\d+\s*(?:day|week|month|hour)s?\s*ago|today|yesterday|just now)", card_text, re.I)
                    date_str = date_match.group(1) if date_match else "Recent"

                    # === Date Range Filter: Exclude jobs older than 1 month ===
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
                        source="Internshala (India)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Internshala: {e}")

        return jobs
