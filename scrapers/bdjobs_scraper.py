import json
import logging
import re
import time
import urllib.parse
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

from core.models.job import ScrapedJob
from core.utils.date_parser import is_posted_within_last_month

logger = logging.getLogger(__name__)


class BdjobsScraper:
    """Scraper for Bdjobs.com (Bangladesh's #1 leading job portal)."""

    BASE_URL = "https://jobs.bdjobs.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Bdjobs for vacancies matching candidate keywords, filtering jobs <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
            "Referer": "https://jobs.bdjobs.com/",
        }

        logger.info(f"Fetching Bdjobs homepage and job cache: {self.BASE_URL}")

        try:
            resp = requests.get(self.BASE_URL, impersonate="chrome", headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Bdjobs returned status {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            state_tag = soup.find("script", id="ng-state")

            all_bd_jobs: list[dict] = []
            if state_tag and state_tag.string:
                try:
                    ng_state = json.loads(state_tag.string)
                    cache = ng_state.get("jobSearchCache", {})
                    for cache_key, cache_val in cache.items():
                        if isinstance(cache_val, dict) and "data" in cache_val:
                            data_items = cache_val.get("data", [])
                            if isinstance(data_items, list):
                                all_bd_jobs.extend(data_items)
                except Exception as ex:
                    logger.warning(f"Failed to parse Bdjobs ng-state: {ex}")

            # If no state tag, fallback to parsing job links
            if not all_bd_jobs:
                links = soup.find_all("a", href=lambda h: h and ("/jobdetails.asp" in h or "/job/" in h))
                for a in links:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not title or not href:
                        continue
                    full_id = f"bdjobs_{hash(href)}"
                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)
                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                    jobs.append(
                        ScrapedJob(
                            id=full_id,
                            title=title,
                            company="Bdjobs Employer",
                            location="Bangladesh",
                            date_posted="Recent",
                            description_snippet="",
                            url=job_url,
                            source="Bdjobs (Bangladesh)",
                            matched_keyword=keywords[0] if keywords else "Software",
                        )
                    )

            # Match and filter jobs from extracted JSON data
            keywords_lower = [kw.lower() for kw in keywords]
            for item in all_bd_jobs:
                job_id = str(item.get("Jobid") or "")
                if not job_id:
                    continue
                full_id = f"bdjobs_{job_id}"

                if full_id in self.seen_job_ids:
                    continue
                self.seen_job_ids.add(full_id)

                title = item.get("jobTitle") or "Software Vacancy"
                company = item.get("companyName") or "Confidential"
                location = item.get("location") or "Bangladesh"
                publish_date = item.get("publishDate") or ""
                deadline = item.get("deadline") or ""
                context = BeautifulSoup(item.get("jobContext") or "", "html.parser").get_text(strip=True)
                edu = BeautifulSoup(item.get("eduRec") or "", "html.parser").get_text(strip=True)
                exp = item.get("experience") or ""
                desc = f"{context} | Exp: {exp} | Edu: {edu}".strip(" | ")

                # Check if matched any keyword or is tech-related
                matched_kw = None
                combined_text = f"{title} {desc}".lower()
                for kw in keywords_lower:
                    if kw in combined_text:
                        matched_kw = kw
                        break

                # If candidate keywords are specific and not matched, keep software/tech jobs
                if not matched_kw:
                    if any(t in combined_text for t in ["software", "developer", "engineer", "it", "programmer", "data", "web"]):
                        matched_kw = keywords[0] if keywords else "Tech"
                    else:
                        continue

                # Date freshness check
                date_str = publish_date[:10] if publish_date else "Recent"
                if publish_date and not is_posted_within_last_month(publish_date[:10], max_days=30):
                    continue

                job_url = f"https://jobs.bdjobs.com/jobdetails.asp?id={job_id}"

                jobs.append(
                    ScrapedJob(
                        id=full_id,
                        title=title,
                        company=company,
                        location=f"{location}, Bangladesh",
                        career_level=exp or None,
                        date_posted=date_str,
                        description_snippet=desc[:350],
                        url=job_url,
                        source="Bdjobs (Bangladesh)",
                        matched_keyword=matched_kw,
                    )
                )

                if len(jobs) >= max_jobs:
                    break

        except Exception as e:
            logger.error(f"Error scraping Bdjobs: {e}")

        return jobs
