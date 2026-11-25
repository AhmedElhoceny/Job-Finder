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


class EmploiticScraper:
    """Scraper for Emploitic.com (Algeria's leading employment platform)."""

    BASE_URL = "https://www.emploitic.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes Emploitic search results for given keywords, filtering for jobs <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,ar;q=0.8,en;q=0.7",
            "Referer": "https://www.emploitic.com/",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/offres-d-emploi?keyword={encoded}"
            logger.info(f"Fetching Emploitic URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"Emploitic returned status {resp.status_code} for {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                links = [
                    a for a in soup.find_all("a", href=True)
                    if "/offres-d-emploi/" in a["href"]
                    and not a["href"].endswith(("/fonction", "/secteur", "/region"))
                    and a.get_text(strip=True)
                ]

                for a in links:
                    raw_text = a.get_text(strip=True)
                    href = a["href"]

                    # Extract job ID from href suffix e.g. -307v8
                    id_match = re.search(r"-([a-zA-Z0-9]+)$", href)
                    raw_id = id_match.group(1) if id_match else str(hash(href))
                    full_id = f"emploitic_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    card = a.find_parent("div", class_=lambda c: c and ("card" in c or "item" in c or "job" in c or "row" in c)) or a.parent.parent
                    card_text = card.get_text(separator=" | ", strip=True) if card else ""

                    # Split card text into metadata
                    parts = [p.strip() for p in card_text.split("|") if p.strip()]
                    title = parts[0] if parts else raw_text
                    company = parts[1] if len(parts) > 1 and parts[1] != title else "Entreprise en Algérie"
                    location = parts[2] if len(parts) > 2 else "Alger, Algérie"

                    # Check for date (Aujourd'hui, Hier, Il y a ...)
                    date_match = re.search(r"(aujourd'hui|hier|il y a\s+\d+\s+jours?|\d{1,2}\s+[a-zA-Z\u00C0-\u00FF]+)", card_text, re.I)
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
                        source="Emploitic (Algeria)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping Emploitic: {e}")

        return jobs
