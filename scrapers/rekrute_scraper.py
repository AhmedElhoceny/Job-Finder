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


class ReKruteScraper:
    """Scraper for ReKrute.com (Morocco's premier executive and professional job portal)."""

    BASE_URL = "https://www.rekrute.com"

    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(self, keywords: list[str], max_jobs: int = 25) -> list[ScrapedJob]:
        """Scrapes ReKrute for matching vacancies in Morocco, strictly filtering jobs <= 30 days old."""
        jobs: list[ScrapedJob] = []

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.rekrute.com/",
        }

        for kw in keywords[:3]:
            encoded = urllib.parse.quote_plus(kw.strip())
            url = f"{self.BASE_URL}/offres-emploi-maroc.html?keyword={encoded}"
            logger.info(f"Fetching ReKrute URL: {url}")

            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"ReKrute returned status {resp.status_code} for {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select(".post-id") or soup.find_all("li", class_=lambda c: c and "post-id" in c)

                for card in cards:
                    a = card.find("a", class_=lambda cl: cl and "titreJob" in cl) or card.find("a", href=lambda h: h and "offre-emploi" in h)
                    if not a:
                        continue

                    title_text = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not href or not title_text or "Lancer 4K" in title_text:
                        continue

                    job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    id_match = re.search(r"-(\d+)\.html", href)
                    raw_id = id_match.group(1) if id_match else str(hash(job_url))
                    full_id = f"rekrute_{raw_id}"

                    if full_id in self.seen_job_ids:
                        continue
                    self.seen_job_ids.add(full_id)

                    # Title format often: "Job Title | City (Maroc)"
                    title = title_text
                    location = "Morocco"
                    if " | " in title_text:
                        parts = title_text.split(" | ")
                        title = parts[0].strip()
                        location = parts[1].strip()

                    card_text = card.get_text(separator=" | ", strip=True)

                    # Extract company name from card
                    company_el = card.find("img", title=True)
                    company = company_el["title"] if company_el and company_el.get("title") else "Confidential"

                    # Date detection
                    date_match = re.search(r"(\d{1,2}\s+[a-zA-Z\u00C0-\u00FF]+\s*\d{0,4}|aujourd'hui|hier|il y a\s+\d+\s+jours?)", card_text, re.I)
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
                        source="ReKrute (Morocco)",
                        matched_keyword=kw,
                    )
                    jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

                time.sleep(self.request_delay)

            except Exception as e:
                logger.error(f"Error scraping ReKrute: {e}")

        return jobs
