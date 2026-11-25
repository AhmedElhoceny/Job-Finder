import json
import logging
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

from googlenewsdecoder import gnewsdecoder

from config.settings import get_settings
from core.models.job import ScrapedJob
from core.utils.date_parser import is_posted_within_last_month

logger = logging.getLogger(__name__)


class LinkedInPostsScraper:
    """Scrapes actual LinkedIn hiring posts published by HRs, recruiters,

    engineering managers, and founders (the hidden job market).

    Extracts:
    - Real LinkedIn social feed posts (https://www.linkedin.com/posts/...)
    - Recruiter / HR author names
    - Post announcements, requirements, and contact emails
    - Publication dates strictly verified within max_days (<= 30 days)
    """

    def __init__(self, li_at_cookie: Optional[str] = None, request_delay: float = 1.0):
        settings = get_settings()
        self.li_at = li_at_cookie or settings.linkedin_li_at or ""
        self.request_delay = request_delay
        self.seen_post_ids: set[str] = set()

    def scrape_keywords(
        self,
        keywords: list[str],
        max_days: int = 30,
        max_posts: Optional[int] = None,
    ) -> list[ScrapedJob]:
        """Scrapes LinkedIn hiring posts matching keywords within max_days (<= 30 days)."""
        posts: list[ScrapedJob] = []

        # 1. If li_at cookie is configured, try authenticated Voyager API first
        if self.li_at:
            logger.info("LinkedIn li_at cookie detected. Attempting authenticated feed search...")
            try:
                auth_posts = self._scrape_voyager_api(keywords=keywords, max_days=max_days, max_posts=max_posts)
                if auth_posts:
                    return auth_posts
            except Exception as e:
                logger.warning(f"Voyager API search failed ({e}), falling back to public mode.")

        # 2. Public mode (No login or credentials required)
        posts = self._scrape_public_posts(keywords=keywords, max_days=max_days, max_posts=max_posts)
        return posts

    def _scrape_public_posts(
        self,
        keywords: list[str],
        max_days: int = 30,
        max_posts: Optional[int] = None,
    ) -> list[ScrapedJob]:
        """Discovers public LinkedIn hiring posts written by recruiters, HRs, and founders.

        Uses news syndication indexing of actual linkedin.com/posts and decodes
        canonical post URLs with googlenewsdecoder. Strictly filters for posts
        published <= max_days (default 30 days).
        """
        posts: list[ScrapedJob] = []

        for kw in keywords:
            if max_posts is not None and len(posts) >= max_posts:
                break

            # Targeted queries for actual HR / recruiter job announcements
            query_templates = [
                f'site:linkedin.com/posts "hiring" "{kw}"',
                f'site:linkedin.com/posts "we are hiring" "{kw}"',
            ]

            for q_str in query_templates:
                if max_posts is not None and len(posts) >= max_posts:
                    break

                encoded_q = urllib.parse.quote_plus(q_str)
                rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
                logger.info(f"Scanning LinkedIn HR hiring posts for '{kw}' (<= {max_days}d)...")

                try:
                    resp = requests.get(rss_url, impersonate="chrome", timeout=15)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "xml")
                    raw_items = soup.find_all("item")

                    # Filter items strictly by pubDate <= max_days first
                    valid_items = []
                    for it in raw_items:
                        pub_el = it.find("pubDate")
                        pub_str = pub_el.get_text(strip=True) if pub_el else ""
                        if pub_str and not is_posted_within_last_month(pub_str, max_days=max_days):
                            continue
                        valid_items.append(it)

                    logger.info(f"Found {len(valid_items)} candidate posts <= {max_days}d. Resolving canonical LinkedIn URLs...")

                    # Decode URLs concurrently with thread pool
                    links_to_decode = [it.find("link").get_text(strip=True) for it in valid_items if it.find("link")]
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        decoded_results = list(executor.map(gnewsdecoder, links_to_decode))

                    for it, dec in zip(valid_items, decoded_results):
                        if max_posts is not None and len(posts) >= max_posts:
                            break

                        pub_el = it.find("pubDate")
                        pub_str = pub_el.get_text(strip=True) if pub_el else "Recent"
                        raw_title = it.find("title").get_text(strip=True) if it.find("title") else ""
                        raw_desc = it.find("description").get_text(strip=True) if it.find("description") else ""

                        post_url = dec.get("decoded_url") if (isinstance(dec, dict) and dec.get("success")) else None
                        if not post_url or ("linkedin.com/posts/" not in post_url and "activity-" not in post_url):
                            continue

                        post_url = post_url.split("?")[0]

                        # Extract unique post ID (activity-XXXX or share-XXXX)
                        id_match = re.search(r"(?:activity|share|post)-(\d+)", post_url) or re.search(r"/posts/([a-zA-Z0-9_-]+)", post_url)
                        raw_id = id_match.group(1) if id_match else str(hash(post_url))
                        full_id = f"linkedin_post_{raw_id}"

                        if full_id in self.seen_post_ids:
                            continue
                        self.seen_post_ids.add(full_id)

                        # Clean Title, Author & Description
                        clean_title = re.sub(r"\s*-\s*LinkedIn\s*$", "", raw_title, flags=re.I).strip()
                        parts = [p.strip() for p in clean_title.split("|") if p.strip()]

                        author = "LinkedIn Recruiter / Hiring Team"
                        headline = clean_title
                        if len(parts) >= 2:
                            headline = parts[0]
                            author = parts[1]

                        # Extract email if mentioned in snippet
                        clean_desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ", strip=True)
                        emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", clean_desc)
                        contact_info = f"Contact: {emails[0]}" if emails else "Apply via LinkedIn Post"

                        full_snippet = f"{clean_desc} | {contact_info}"

                        job = ScrapedJob(
                            id=full_id,
                            title=f"[HR Post] {headline[:80]}",
                            company=author,
                            location="LinkedIn Feed / Remote",
                            date_posted=pub_str,
                            description_snippet=full_snippet[:400],
                            url=post_url,
                            source="LinkedIn (Post)",
                            matched_keyword=kw,
                        )
                        posts.append(job)

                    time.sleep(self.request_delay)

                except Exception as e:
                    logger.error(f"Error scraping LinkedIn hiring posts ({q_str}): {e}")

        return posts

    def _scrape_voyager_api(
        self,
        keywords: list[str],
        max_days: int = 30,
        max_posts: Optional[int] = None,
    ) -> list[ScrapedJob]:
        """Optional authenticated feed search via LinkedIn Voyager internal API."""
        posts: list[ScrapedJob] = []

        headers = {
            "Accept": "application/vnd.linkedin.normalized+json+2.1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "x-restli-protocol-version": "2.0.0",
        }
        cookies = {"li_at": self.li_at}

        for kw in keywords:
            if max_posts is not None and len(posts) >= max_posts:
                break

            url = f"https://www.linkedin.com/voyager/api/search/dash/clusters?q=all&query=hiring%20{urllib.parse.quote_plus(kw)}"
            try:
                resp = requests.get(url, impersonate="chrome", headers=headers, cookies=cookies, timeout=12)
                if resp.status_code != 200:
                    logger.warning(f"LinkedIn Voyager returned status {resp.status_code}")
                    return []

                data = resp.json()
                elements = data.get("elements", [])

                for el in elements:
                    # Parse entity cards
                    for item in el.get("items", []):
                        entity = item.get("item", {}).get("entityResult", {})
                        if not entity:
                            continue

                        title = entity.get("title", {}).get("text") or f"[Hiring Post] {kw}"
                        subtitle = entity.get("primarySubtitle", {}).get("text") or "LinkedIn Member"
                        nav_url = entity.get("navigationUrl") or ""

                        if not nav_url:
                            continue

                        full_id = f"linkedin_post_{hash(nav_url)}"
                        if full_id in self.seen_post_ids:
                            continue
                        self.seen_post_ids.add(full_id)

                        summary = entity.get("summary", {}).get("text") or ""

                        posts.append(
                            ScrapedJob(
                                id=full_id,
                                title=f"[Post] {title[:70]}",
                                company=subtitle,
                                location="LinkedIn Post",
                                date_posted="Recent",
                                description_snippet=summary[:350],
                                url=nav_url,
                                source="LinkedIn (Post)",
                                matched_keyword=kw,
                            )
                        )

                        if max_posts is not None and len(posts) >= max_posts:
                            break

            except Exception as e:
                logger.error(f"Voyager API search exception: {e}")

        return posts
