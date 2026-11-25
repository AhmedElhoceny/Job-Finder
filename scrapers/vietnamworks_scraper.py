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


class VietnamWorksScraper:
    """Scraper for VietnamWorks.com (Vietnam's #1 premier job recruitment portal)."""

    BASE_URL = "https://www.vietnamworks.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes VietnamWorks for vacancies matching keywords."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            "Referer": "https://www.vietnamworks.com/",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/tim-viec-lam/tat-ca-viec-lam?q={encoded}"
            logger.info(f"Fetching VietnamWorks URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"VietnamWorks returned status {resp.status_code} for {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                next_tag = soup.find("script", id="__NEXT_DATA__")

                if next_tag and next_tag.string:
                    try:
                        data = json.loads(next_tag.string)
                        jd = data.get("props", {}).get("pageProps", {}).get("jobsData", {})

                        # Collect job objects from all list categories
                        candidates: list[dict] = []
                        for key in ["urgentJobs", "featuredJobs", "bestJobs", "highSalaryJobs"]:
                            candidates.extend(jd.get(key, []))

                        for item in candidates:
                            job_id = str(item.get("jobId") or item.get("id") or "")
                            title = item.get("title") or item.get("jobTitle") or ""
                            if not title:
                                continue

                            full_id = f"vietnamworks_{job_id or hash(title)}"
                            if full_id in self.seen_job_ids:
                                continue
                            self.seen_job_ids.add(full_id)

                            company = item.get("company") or item.get("companyName") or "Company in Vietnam"
                            alias = item.get("alias") or item.get("jobUrl") or ""
                            job_url = f"{self.BASE_URL}/{alias}-jv" if alias else f"{self.BASE_URL}/tim-viec-lam/{job_id}-jv"

                            locations = item.get("workingLocations", [])
                            loc_str = locations[0].get("address") if locations and isinstance(locations[0], dict) else "Vietnam"

                            job = ScrapedJob(
                                id=full_id,
                                title=title,
                                company=company,
                                location=f"{loc_str[:60]}, Vietnam",
                                date_posted="Recent",
                                description_snippet=f"Industry: {item.get('industry', '')}",
                                url=job_url,
                                source="VietnamWorks",
                                matched_keyword=kw,
                            )
                            jobs.append(job)

                            if len(jobs) >= max_jobs:
                                break

                    except Exception as err:
                        logger.warning(f"Failed parsing VietnamWorks __NEXT_DATA__: {err}")

                # Fallback to scraping link tags directly
                if not jobs:
                    links = soup.find_all("a", href=lambda h: h and "-jv" in h)
                    for a in links:
                        title = a.get_text(strip=True)
                        href = a.get("href", "")
                        if not title or not href:
                            continue
                        job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                        full_id = f"vietnamworks_{hash(job_url)}"
                        if full_id in self.seen_job_ids:
                            continue
                        self.seen_job_ids.add(full_id)
                        jobs.append(
                            ScrapedJob(
                                id=full_id,
                                title=title,
                                company="Company in Vietnam",
                                location="Vietnam",
                                date_posted="Recent",
                                description_snippet="",
                                url=job_url,
                                source="VietnamWorks",
                                matched_keyword=kw,
                            )
                        )
                        if len(jobs) >= max_jobs:
                            break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping VietnamWorks: {e}")

        return jobs
