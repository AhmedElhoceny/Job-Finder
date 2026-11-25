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


class MynaviScraper:
    """Scraper for Tenshoku.Mynavi.jp (Japan's leading professional recruitment platform)."""

    BASE_URL = "https://tenshoku.mynavi.jp"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Mynavi for vacancies matching candidate keywords."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8",
            "Referer": "https://tenshoku.mynavi.jp/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for kw in keywords[:3]:
            cleaned_kw = re.sub(r"[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+", "", kw.strip())
            url = f"{self.BASE_URL}/list/kw{cleaned_kw}/"
            logger.info(f"Fetching Mynavi URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Mynavi returned status {resp.status_code} for {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select(".cassetteRecruit") or soup.find_all("div", class_=lambda c: c and "cassette" in c)

                for card in cards:
                    comp_el = card.select_one(".cassetteRecruit__name") or card.select_one("h3")
                    company = comp_el.get_text(strip=True) if comp_el else "Japanese Company"

                    title_el = card.select_one(".cassetteRecruit__copy a") or card.find("a", href=lambda h: h and "/jobinfo-" in h)
                    title = title_el.get_text(strip=True) if title_el else ""
                    href = title_el.get("href", "") if title_el else ""

                    if not href or not title:
                        link_el = card.find("a", href=True)
                        if link_el:
                            href = link_el["href"]
                            title = title or link_el.get_text(strip=True)

                    if not href:
                        continue

                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    id_match = re.search(r"/jobinfo-(\d+)-", href) or re.search(r"(\d+)", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"mynavi_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    card_text = card.get_text(separator=" | ", strip=True)

                    date_match = re.search(r"(\d+\s*日\s*前|本日|昨日|\d{4}/\d{1,2}/\d{1,2})", card_text)
                    date_str = date_match.group(1) if date_match else "Recent"

                    if not is_posted_within_last_month(date_str, max_days=30):
                        continue

                    location = "Tokyo / Japan"
                    for p in card_text.split("|"):
                        if any(c in p for c in ["東京", "大阪", "名古屋", "神奈川", "リモート", "全国"]):
                            location = f"{p.strip()}, Japan"
                            break

                    job = ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=location,
                        date_posted=date_str,
                        description_snippet=card_text[:350],
                        url=job_url,
                        source="Mynavi (Japan)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Mynavi: {e}")

        return jobs
