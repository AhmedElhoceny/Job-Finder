import logging
import re
import time
from typing import Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

from core.models.job import ScrapedJob
from core.utils.date_parser import is_posted_within_last_month, parse_posting_age_days

logger = logging.getLogger(__name__)


class BaytScraper:
    """Scraper for Bayt.com job listings with Cloudflare bypass via curl_cffi."""

    BASE_URL = "https://www.bayt.com"

    def __init__(self, request_delay: float = 1.5):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    @staticmethod
    def keyword_to_slug(keyword: str) -> str:
        """Converts search keyword or role into Bayt URL slug format.

        Example: 'Python Developer' -> 'python-developer'
                 'Senior Backend Engineer' -> 'backend-engineer'
        """
        cleaned = keyword.strip().lower()
        # Remove common modifier words that break slugs
        cleaned = re.sub(r"\b(senior|lead|remote|junior|fresher|staff)\b", "", cleaned).strip()
        # Replace non-alphanumeric with hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
        return slug or "python"

    def scrape_url(self, url: str, matched_keyword: str = "", max_jobs: int = 15) -> list[ScrapedJob]:
        """Fetches a specific Bayt.com search URL and extracts structured job postings."""
        logger.info(f"Fetching Bayt.com URL: {url}")
        jobs: list[ScrapedJob] = []

        try:
            resp = requests.get(url, impersonate="chrome", timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Bayt.com returned status {resp.status_code} for {url}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            job_items = soup.find_all("li", {"data-js-job": True})

            for item in job_items:
                # 1. Job Title & Direct Link
                title_tag = item.select_one("h2 a")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                href = title_tag.get("href", "")
                if not href:
                    continue
                job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                # Extract unique job ID from URL or data attribute
                job_id = item.get("data-job-id")
                if not job_id:
                    match = re.search(r"-(\d+)/?$", href)
                    job_id = match.group(1) if match else str(hash(job_url))
                full_id = f"bayt_{job_id}"

                # Deduplication
                if full_id in self.seen_job_ids:
                    continue
                self.seen_job_ids.add(full_id)

                # 2. Company Name
                comp_tag = item.select_one(".job-company-location-wrapper")
                company = comp_tag.get_text(strip=True) if comp_tag else "Confidential / Hidden"

                # 3. Location & Career Level (from tags section)
                tags_el = item.select_one(".jb-tags")
                tags_text = tags_el.get_text(separator=" | ", strip=True) if tags_el else ""
                parts = [p.strip() for p in tags_text.split("|") if p.strip()]

                location = parts[0] if len(parts) > 0 else "Middle East / Remote"
                career_level = parts[1] if len(parts) > 1 else None

                # 4. Description Snippet
                desc_el = item.select_one(".jb-descr")
                description = desc_el.get_text(strip=True) if desc_el else ""
                if description.startswith("Summary:"):
                    description = description[len("Summary:") :].strip()

                # 5. Date Posted & 1-Month Range Filtering
                date_el = item.select_one(".jb-date") or item.select_one(".jb-footer")
                date_posted = date_el.get_text(strip=True) if date_el else None

                # Exclude any job posted later than 1 month ago (e.g. 30+ days ago)
                if date_posted and not is_posted_within_last_month(date_posted, max_days=30):
                    logger.debug(f"Skipping Bayt job '{title}' - older than 1 month ({date_posted})")
                    continue

                job = ScrapedJob(
                    id=full_id,
                    title=title,
                    company=company,
                    location=location,
                    career_level=career_level,
                    date_posted=date_posted,
                    description_snippet=description,
                    url=job_url,
                    source="Bayt.com",
                    matched_keyword=matched_keyword,
                )
                jobs.append(job)

                if len(jobs) >= max_jobs:
                    break

        except Exception as e:
            logger.error(f"Error scraping Bayt.com ({url}): {e}")

        return jobs

    def scrape_by_keywords(
        self,
        keywords: list[str],
        country: str = "international",
        max_jobs_per_keyword: int = 10,
        max_total_jobs: int = 20,
    ) -> list[ScrapedJob]:
        """Runs searches across multiple keywords/roles and aggregates unique vacancies."""
        all_jobs: list[ScrapedJob] = []

        # Deduplicate slugs to avoid querying the same URL multiple times
        tested_slugs: set[str] = set()

        for kw in keywords:
            if len(all_jobs) >= max_total_jobs:
                break

            slug = self.keyword_to_slug(kw)
            if not slug or slug in tested_slugs:
                continue
            tested_slugs.add(slug)

            search_url = f"{self.BASE_URL}/en/{country}/jobs/{slug}-jobs/"
            found = self.scrape_url(search_url, matched_keyword=kw, max_jobs=max_jobs_per_keyword)
            all_jobs.extend(found)

            time.sleep(self.request_delay)

        return all_jobs[:max_total_jobs]
