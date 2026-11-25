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


class OneZeroFourScraper:
    """Scraper for 104 Job Bank (104.com.tw - Taiwan's largest job bank and human resource portal)."""

    BASE_URL = "https://www.104.com.tw"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes 104 Job Bank for matching vacancies in Taiwan."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
            "Referer": "https://www.104.com.tw/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/jobs/search/?keyword={encoded}"
            logger.info(f"Fetching 104 Job Bank URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                articles = soup.find_all("article", class_=lambda c: c and "job-list-item" in c) or soup.find_all("a", href=lambda h: h and "/job/" in h)

                for item in articles:
                    a = item if item.name == "a" else item.find("a", href=lambda h: h and "/job/" in h)
                    if not a:
                        continue

                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not href or not title:
                        continue

                    job_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

                    id_match = re.search(r"/job/([a-zA-Z0-9]+)", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"104_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    card = item if item.name != "a" else a.parent.parent
                    card_text = card.get_text(separator=" | ", strip=True) if card else ""

                    date_match = re.search(r"(\d{1,2}/\d{1,2}|\d+\s*天前|今天)", card_text)
                    date_str = date_match.group(1) if date_match else "Recent"

                    if not is_posted_within_last_month(date_str, max_days=30):
                        continue

                    parts = [p.strip() for p in card_text.split("|") if p.strip()]
                    company = parts[1] if len(parts) > 1 and parts[1] != title else "Taiwan Tech Company"
                    location = "Taiwan / Remote"
                    for p in parts:
                        if any(c in p for c in ["台北", "新北", "新竹", "台中", "台南", "高雄"]):
                            location = f"{p}, Taiwan"
                            break

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str,
                        description_snippet=card_text[:350],
                        url=job_url,
                        source="104 Job Bank (Taiwan)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping 104 Job Bank: {e}")

        return jobs
