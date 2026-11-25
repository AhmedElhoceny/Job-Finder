import logging
import re
import time
from typing import Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

from core.models.job import ScrapedJob
from core.utils.date_parser import is_posted_within_last_month

logger = logging.getLogger(__name__)


class GulfTalentScraper:
    """Scraper for GulfTalent.com (Premier job site for UAE, Saudi Arabia, Qatar, and GCC)."""

    BASE_URL = "https://www.gulftalent.com"

    def __init__(self, request_delay: float = 1.5):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_category(self, category: str = "software", max_pages: int = 1) -> list[ScrapedJob]:
        """Scrapes GulfTalent software job listings, strictly filtering for jobs <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.gulftalent.com/",
        }

        url = f"{self.BASE_URL}/jobs/category/{category}"
        logger.info(f"Fetching GulfTalent URL: {url}")

        try:
            resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"GulfTalent returned status {resp.status_code} for {url}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            job_links = soup.find_all("a", href=lambda h: h and "/jobs/" in h and any(c.isdigit() for c in h))

            for a in job_links:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if not href or not title:
                    continue
                job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                # Extract unique ID
                id_match = re.search(r"-(\d+)/?$", href)
                raw_id = id_match.group(1) if id_match else str(hash(job_url))
                full_id = f"gulftalent_{raw_id}"

                if full_id in self.seen_job_ids:
                    continue
                self.seen_job_ids.add(full_id)

                # Locate parent row
                parent = (
                    a.find_parent("tr")
                    or a.find_parent("div", class_=lambda c: c and ("panel" in c or "row" in c))
                    or a.parent.parent
                )
                parent_text = parent.get_text(separator=" | ", strip=True) if parent else ""
                parts = [p.strip() for p in parent_text.split("|") if p.strip()]

                # Extract details: GulfTalent format is [Title, Company, Location, Date]
                company = parts[1] if len(parts) > 1 and parts[1] != title else "Confidential"
                location = parts[2] if len(parts) > 2 else "UAE / GCC"

                # Extract Date (e.g. '24 Nov', '17 Nov', '12 Nov')
                date_match = re.search(r"\b(\d{1,2}\s+[a-zA-Z]{3,9})\b", parent_text)
                date_str = date_match.group(1) if date_match else None

                # === Date Range Filter: Exclude jobs posted older than 1 month ===
                if date_str and not is_posted_within_last_month(date_str, max_days=30):
                    logger.debug(f"Skipping GulfTalent job '{title}' - older than 1 month ({date_str})")
                    continue

                job = ScrapedJob(
                    id=full_id,
                    title=title,
                    company=company,
                    location=location,
                    date_posted=date_str or "Recent",
                    description_snippet=parent_text[:300],
                    url=job_url,
                    source="GulfTalent",
                    matched_keyword=category,
                )
                jobs.append(job)

        except Exception as e:
            logger.error(f"Error scraping GulfTalent ({url}): {e}")

        return jobs
