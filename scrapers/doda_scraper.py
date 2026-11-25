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


class DodaScraper:
    """Scraper for Doda.jp (One of Japan's largest career change and engineering job boards)."""

    BASE_URL = "https://doda.jp"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Doda.jp for vacancies matching candidate keywords."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8",
            "Referer": "https://doda.jp/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/DodaFront/View/JobSearchList.action?kw={encoded}"
            logger.info(f"Fetching Doda URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Doda returned status {resp.status_code} for {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=lambda h: h and "/JobSearchDetail/j_jid__" in h)

                for a in links:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not href or not title or len(title) < 4:
                        continue

                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    id_match = re.search(r"j_jid__(\d+)", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"doda_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    card = a.find_parent("div", class_=lambda c: c and ("layoutBox" in c or "part" in c or "job" in c or "box" in c)) or a.parent.parent
                    card_text = card.get_text(separator=" | ", strip=True) if card else ""

                    date_match = re.search(r"(\d+\s*日\s*前|本日|昨日|\d{4}/\d{1,2}/\d{1,2})", card_text)
                    date_str = date_match.group(1) if date_match else "Recent"

                    if not is_posted_within_last_month(date_str, max_days=30):
                        continue

                    parts = [p.strip() for p in card_text.split("|") if p.strip()]
                    company = parts[0] if parts and parts[0] != title else "Japanese Corporation"
                    location = "Tokyo / Japan"
                    for p in parts:
                        if any(c in p for c in ["東京", "大阪", "名古屋", "神奈川", "リモート"]):
                            location = f"{p}, Japan"
                            break

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str,
                        description_snippet=card_text[:350],
                        url=job_url,
                        source="Doda (Japan)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Doda: {e}")

        return jobs
