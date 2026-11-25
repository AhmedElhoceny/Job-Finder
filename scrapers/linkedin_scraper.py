import logging
from typing import Optional

from core.models.job import ScrapedJob
from scrapers.linkedin_jobs_scraper import LinkedInJobsScraper
from scrapers.linkedin_posts_scraper import LinkedInPostsScraper

logger = logging.getLogger(__name__)


class LinkedInScraper:
    """Unified LinkedIn Scraper coordinating both formal Job Listings

    and Recruiter Hiring Posts without requiring an account.
    """

    def __init__(
        self,
        li_at_cookie: Optional[str] = None,
        request_delay: float = 1.2,
    ):
        self.jobs_scraper = LinkedInJobsScraper(request_delay=request_delay)
        self.posts_scraper = LinkedInPostsScraper(li_at_cookie=li_at_cookie, request_delay=request_delay)

    def scrape_jobs(
        self,
        keywords: list[str],
        locations: Optional[list[str]] = None,
        max_days: int = 30,
        max_jobs: Optional[int] = None,
        remote_only: bool = False,
    ) -> list[ScrapedJob]:
        """Scrapes formal LinkedIn job listings strictly within max_days (<= 30 days)."""
        return self.jobs_scraper.scrape_keywords(
            keywords=keywords,
            locations=locations,
            max_days=max_days,
            max_jobs=max_jobs,
            remote_only=remote_only,
        )

    def scrape_posts(
        self,
        keywords: list[str],
        max_days: int = 30,
        max_posts: Optional[int] = None,
    ) -> list[ScrapedJob]:
        """Scrapes recruiter and hiring manager posts from LinkedIn within max_days (<= 30 days)."""
        return self.posts_scraper.scrape_keywords(
            keywords=keywords,
            max_days=max_days,
            max_posts=max_posts,
        )

    def scrape_all(
        self,
        keywords: list[str],
        locations: Optional[list[str]] = None,
        max_days: int = 30,
        max_jobs: Optional[int] = None,
        max_posts: Optional[int] = None,
        remote_only: bool = False,
    ) -> list[ScrapedJob]:
        """Runs both LinkedIn Jobs and LinkedIn Posts scrapers and returns all aggregated results

        strictly filtered by date (<= max_days, default 30 days) without arbitrary count caps.
        """
        all_results: list[ScrapedJob] = []

        # 1. Scrape Formal Jobs
        try:
            logger.info("--> Running LinkedIn Jobs Scraper (Date-limited <= %sd)...", max_days)
            jobs = self.scrape_jobs(
                keywords=keywords,
                locations=locations,
                max_days=max_days,
                max_jobs=max_jobs,
                remote_only=remote_only,
            )
            all_results.extend(jobs)
            logger.info(f"LinkedIn Jobs returned {len(jobs)} vacancies.")
        except Exception as e:
            logger.error(f"LinkedIn Jobs scraping failed: {e}")

        # 2. Scrape Hiring Posts
        try:
            logger.info("--> Running LinkedIn Posts Scraper (Date-limited <= %sd)...", max_days)
            posts = self.scrape_posts(
                keywords=keywords,
                max_days=max_days,
                max_posts=max_posts,
            )
            all_results.extend(posts)
            logger.info(f"LinkedIn Posts returned {len(posts)} hiring posts.")
        except Exception as e:
            logger.error(f"LinkedIn Posts scraping failed: {e}")

        return all_results
