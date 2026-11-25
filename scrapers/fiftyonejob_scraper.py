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


class FiftyOneJobScraper:
    """Scraper for 51job.com (China's leading online recruitment services platform)."""

    BASE_URL = "https://we.51job.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes 51job for vacancies matching candidate keywords."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8",
            "Referer": "https://we.51job.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/pc/search?jobArea=000000&keyword={encoded}"
            logger.info(f"Fetching 51job URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=lambda h: h and ("/job/" in h or "jobs.51job.com" in h))

                for a in links:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not href or not title or len(title) < 3:
                        continue

                    job_url = href if href.startswith("http") else f"https:{href}"

                    id_match = re.search(r"/(\d+)\.html", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"51job_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    card = a.find_parent("div", class_=lambda c: c and ("item" in c or "job" in c or "card" in c)) or a.parent.parent
                    card_text = card.get_text(separator=" | ", strip=True) if card else ""

                    date_match = re.search(r"(\d+\s*天前|今天|昨天|\d{4}-\d{2}-\d{2})", card_text)
                    date_str = date_match.group(1) if date_match else "Recent"

                    if not is_posted_within_last_month(date_str, max_days=30):
                        continue

                    parts = [p.strip() for p in card_text.split("|") if p.strip()]
                    company = parts[1] if len(parts) > 1 and parts[1] != title else "Chinese Enterprise"
                    location = "China"
                    for p in parts:
                        if any(c in p for c in ["北京", "上海", "深圳", "广州", "杭州", "成都"]):
                            location = f"{p}, China"
                            break

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str,
                        description_snippet=card_text[:350],
                        url=job_url,
                        source="51job (China)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping 51job: {e}")

        return jobs
