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


class LinkedInJobsScraper:
    """Scrapes live formal job postings from LinkedIn without requiring login.

    Uses public web search endpoints with Chrome TLS impersonation and strict
    freshness filtering (<= 30 days) across paginated results.
    """

    BASE_URL = "https://www.linkedin.com/jobs/search"

    DEFAULT_LOCATIONS = [
        "Worldwide",
        "Egypt",
        "United Arab Emirates",
        "Saudi Arabia",
    ]

    def __init__(self, request_delay: float = 1.5):
        self.request_delay = request_delay
        self.seen_job_ids: set[str] = set()

    def scrape_keywords(
        self,
        keywords: list[str],
        locations: Optional[list[str]] = None,
        max_days: int = 30,
        max_jobs: Optional[int] = None,
        max_pages_per_query: int = 10,
        remote_only: bool = False,
    ) -> list[ScrapedJob]:
        """Queries LinkedIn job search for given keywords across specified locations.

        Paginates through search results collecting ALL jobs within max_days
        (default 30 days). Stops when jobs exceed the date window or results end.
        """
        jobs: list[ScrapedJob] = []
        target_locations = locations or self.DEFAULT_LOCATIONS

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        # LinkedIn time filter mapping in seconds:
        # 1 day = 86400, 7 days = 604800, 30 days = 2592000
        time_filter = "r2592000"
        if max_days <= 1:
            time_filter = "r86400"
        elif max_days <= 7:
            time_filter = "r604800"

        for kw in keywords:
            if max_jobs is not None and len(jobs) >= max_jobs:
                break

            for loc in target_locations:
                if max_jobs is not None and len(jobs) >= max_jobs:
                    break

                logger.info(f"Scraping LinkedIn Jobs for '{kw}' in '{loc}' (posted within <= {max_days} days)...")

                for page in range(max_pages_per_query):
                    if max_jobs is not None and len(jobs) >= max_jobs:
                        break

                    start_offset = page * 25
                    params = {
                        "keywords": kw.strip(),
                        "location": loc.strip(),
                        "f_TPR": time_filter,
                        "position": "1",
                        "pageNum": str(page),
                        "start": str(start_offset),
                    }
                    if remote_only or "remote" in kw.lower():
                        params["f_WT"] = "2"  # 2 = Remote on LinkedIn

                    query_string = urllib.parse.urlencode(params)
                    search_url = f"{self.BASE_URL}?{query_string}"
                    logger.debug(f"Fetching LinkedIn Jobs URL (page {page}): {search_url}")

                    try:
                        resp = requests.get(search_url, impersonate="chrome", headers=headers, timeout=15)
                        if resp.status_code in (429, 999):
                            logger.warning(f"LinkedIn Jobs returned status {resp.status_code}. Backing off 4s and retrying...")
                            time.sleep(4.0)
                            resp = requests.get(search_url, impersonate="chrome", headers=headers, timeout=15)

                        if resp.status_code != 200:
                            logger.warning(f"LinkedIn Jobs returned status {resp.status_code} for {search_url}")
                            break

                        soup = BeautifulSoup(resp.text, "html.parser")
                        cards = soup.find_all("div", class_=lambda cl: cl and "base-card" in cl) or soup.find_all("li")

                        if not cards:
                            logger.debug(f"No cards returned on page {page} for '{kw}' in '{loc}'. Stopping pagination.")
                            break

                        new_fresh_jobs_in_page = 0
                        stale_jobs_in_page = 0

                        for c in cards:
                            link_el = (
                                c.find("a", class_=lambda cl: cl and "base-card__full-link" in cl)
                                or c.find("a", href=lambda h: h and "/jobs/view/" in h)
                            )
                            if not link_el or not link_el.get("href"):
                                continue

                            raw_href = link_el["href"]
                            clean_url = raw_href.split("?")[0]

                            # Extract unique LinkedIn job ID
                            id_match = re.search(r"-(\d+)(?:/|$)", clean_url) or re.search(r"/view/(\d+)", clean_url)
                            raw_id = id_match.group(1) if id_match else str(hash(clean_url))
                            full_id = f"linkedin_job_{raw_id}"

                            if full_id in self.seen_job_ids:
                                continue
                            self.seen_job_ids.add(full_id)

                            title_el = (
                                c.find("h3", class_=lambda cl: cl and "base-search-card__title" in cl)
                                or c.find("h3")
                            )
                            title = title_el.get_text(strip=True) if title_el else ""
                            if not title or len(title) < 3:
                                continue

                            comp_el = (
                                c.find("h4", class_=lambda cl: cl and "base-search-card__subtitle" in cl)
                                or c.find("h4")
                                or c.find("a", class_=lambda cl: cl and "hidden-nested-link" in cl)
                            )
                            company = comp_el.get_text(strip=True) if comp_el else "LinkedIn Employer"

                            loc_el = (
                                c.find("span", class_=lambda cl: cl and "job-search-card__location" in cl)
                                or c.find("span", class_=lambda cl: cl and "location" in cl)
                            )
                            job_location = loc_el.get_text(strip=True) if loc_el else loc

                            date_el = c.find("time")
                            date_str = date_el.get_text(strip=True) if date_el else "Recent"

                            # Strict Date Limitation check: must be <= max_days
                            if not is_posted_within_last_month(date_str, max_days=max_days):
                                stale_jobs_in_page += 1
                                logger.debug(f"Filtered out LinkedIn job '{title}' - older than {max_days} days ({date_str})")
                                continue

                            card_text = c.get_text(separator=" | ", strip=True)

                            job = ScrapedJob(
                                id=full_id,
                                title=title,
                                company=company,
                                location=job_location,
                                date_posted=date_str,
                                description_snippet=card_text[:350],
                                url=clean_url,
                                source="LinkedIn (Job)",
                                matched_keyword=kw,
                            )
                            jobs.append(job)
                            new_fresh_jobs_in_page += 1

                            if max_jobs is not None and len(jobs) >= max_jobs:
                                break

                        logger.info(
                            f"  Page {page}: +{new_fresh_jobs_in_page} fresh jobs <= {max_days}d "
                            f"(total collected: {len(jobs)})"
                        )

                        # Termination condition by DATE or exhaustion:
                        # If no fresh jobs were found on this page, or all were stale / duplicates, stop pagination
                        if new_fresh_jobs_in_page == 0:
                            logger.debug("No new fresh jobs found on this page. Stopping pagination for this query.")
                            break

                        time.sleep(self.request_delay)

                    except Exception as e:
                        logger.error(f"Error scraping LinkedIn Jobs ({search_url}): {e}")
                        break

        return jobs
