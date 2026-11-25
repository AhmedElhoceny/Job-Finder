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


class SaraminScraper:
    """Scraper for Saramin.co.kr (South Korea's #1 premier recruitment platform)."""

    BASE_URL = "https://www.saramin.co.kr"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Saramin for matching vacancies in South Korea."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.saramin.co.kr/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/zf_user/search/recruit?searchword={encoded}"
            logger.info(f"Fetching Saramin URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Saramin returned status {resp.status_code} for {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".item_recruit")

                for it in items:
                    title_tag = it.select_one(".job_tit a")
                    if not title_tag:
                        continue

                    title = title_tag.get_text(strip=True)
                    href = title_tag.get("href", "")
                    if not href or not title:
                        continue

                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    id_match = re.search(r"rec_idx=(\d+)", href) or re.search(r"/(\d+)(?:\?|$)", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"saramin_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    comp_tag = it.select_one(".corp_name a")
                    company = comp_tag.get_text(strip=True) if comp_tag else "Korean Enterprise"

                    # Condition tags: location, experience, education, employment type
                    cond_tag = it.select_one(".job_condition")
                    cond_text = cond_tag.get_text(separator=" | ", strip=True) if cond_tag else ""
                    parts = [p.strip() for p in cond_text.split("|") if p.strip()]

                    location = f"{parts[0]}, South Korea" if parts else "Seoul, South Korea"
                    career_level = parts[1] if len(parts) > 1 else None

                    date_tag = it.select_one(".job_date .date")
                    date_str = date_tag.get_text(strip=True) if date_tag else "Recent"

                    if not is_posted_within_last_month(date_str, max_days=30):
                        continue

                    desc_tag = it.select_one(".job_sector")
                    desc = desc_tag.get_text(separator=", ", strip=True) if desc_tag else cond_text

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        career_level=career_level,
                        date_posted=date_str,
                        description_snippet=desc[:350],
                        url=job_url,
                        source="Saramin (South Korea)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Saramin: {e}")

        return jobs
