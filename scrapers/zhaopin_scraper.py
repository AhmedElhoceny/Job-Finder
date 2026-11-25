import json
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


class ZhaopinScraper:
    """Scraper for Zhaopin.com (One of China's largest recruitment networks)."""

    BASE_URL = "https://sou.zhaopin.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Zhaopin for matching vacancies in China."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://sou.zhaopin.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/?kw={encoded}"
            logger.info(f"Fetching Zhaopin URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Zhaopin returned status {resp.status_code} for {url}")
                    continue

                # Parse __INITIAL_STATE__ JSON
                idx = resp.text.find("__INITIAL_STATE__=")
                if idx != -1:
                    try:
                        script_end = resp.text.find("</script>", idx)
                        raw_json = resp.text[idx + len("__INITIAL_STATE__="):script_end].strip().rstrip(";")
                        data = json.loads(raw_json)
                        positions = data.get("positionList", [])

                        for p in positions:
                            title = p.get("name") or ""
                            if not title:
                                continue

                            num = str(p.get("number") or p.get("id") or "")
                            full_id = f"zhaopin_{num or hash(title)}"

                            if full_id in self.seen_job_ids:
                                continue
                            self.seen_job_ids.add(full_id)

                            company = p.get("companyName") or "Chinese Tech Enterprise"
                            city = p.get("cityDistrict") or p.get("workCity") or "China"
                            salary = p.get("salaryCount") or ""
                            pub_time = p.get("publishTime") or ""
                            date_str = pub_time[:10] if pub_time else "Recent"

                            if pub_time and not is_posted_within_last_month(pub_time[:10], max_days=30):
                                continue

                            job_url = p.get("positionUrl") or f"https://www.zhaopin.com/jobdetail/{num}.htm"

                            job = ScrapedJob(
                                id=full_id,
                                title=title,
                                company=company,
                                location=f"{city}, China",
                                date_posted=date_str,
                                description_snippet=f"Salary: {salary} | Skills: {p.get('skillLabel', '')}",
                                url=job_url,
                                source="Zhaopin (China)",
                                matched_keyword=kw,
                            )
                            jobs.append(job)

                            if len(jobs) >= max_jobs:
                                break

                    except Exception as err:
                        logger.warning(f"Error parsing Zhaopin JSON state: {err}")

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Zhaopin: {e}")

        return jobs
