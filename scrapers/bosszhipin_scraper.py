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


class BossZhipinScraper:
    """Scraper for Boss Zhipin (BOSS直聘 - China's leading mobile recruitment platform)."""

    BASE_URL = "https://www.zhipin.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Boss Zhipin for vacancies matching candidate keywords."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8",
            "Referer": "https://www.zhipin.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/web/geek/job?query={encoded}&city=100010000"
            logger.info(f"Fetching Boss Zhipin URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=12)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                job_cards = soup.select(".job-card-wrapper") or soup.find_all("li", class_=lambda c: c and "job-card" in c)

                for card in job_cards:
                    title_el = card.select_one(".job-name") or card.find("a", href=lambda h: h and "/job_detail/" in h)
                    title = title_el.get_text(strip=True) if title_el else ""
                    href = title_el.get("href", "") if title_el and title_el.name == "a" else ""
                    if not href:
                        a_tag = card.find("a", href=True)
                        href = a_tag["href"] if a_tag else ""

                    if not title or not href:
                        continue

                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    id_match = re.search(r"/job_detail/([a-zA-Z0-9~]+)\.html", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"bosszhipin_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    comp_el = card.select_one(".company-name")
                    company = comp_el.get_text(strip=True) if comp_el else "Chinese Employer"

                    area_el = card.select_one(".job-area")
                    location = f"{area_el.get_text(strip=True)}, China" if area_el else "China"

                    card_text = card.get_text(separator=" | ", strip=True)

                    date_match = re.search(r"(\d+\s*天前|今天|昨天)", card_text)
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
                        source="BOSS Zhipin (China)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Boss Zhipin: {e}")

        return jobs
