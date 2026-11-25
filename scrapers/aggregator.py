import logging
from typing import Any, Optional

from core.database import JobDatabase
from core.models.job import ScrapedJob

# MENA Scrapers
from scrapers.bayt_scraper import BaytScraper
from scrapers.gulftalent_scraper import GulfTalentScraper
from scrapers.naukrigulf_scraper import NaukrigulfScraper
from scrapers.wuzzuf_scraper import WuzzufScraper
from scrapers.forasna_scraper import ForasnaScraper
from scrapers.akhtaboot_scraper import AkhtabootScraper
from scrapers.tanqeeb_scraper import TanqeebScraper
from scrapers.rekrute_scraper import ReKruteScraper
from scrapers.emploitic_scraper import EmploiticScraper
from scrapers.dubizzle_scraper import DubizzleScraper

# South Asia Scrapers
from scrapers.naukri_scraper import NaukriScraper
from scrapers.foundit_scraper import FounditScraper
from scrapers.internshala_scraper import InternshalaScraper
from scrapers.rozee_scraper import RozeeScraper
from scrapers.bdjobs_scraper import BdjobsScraper

# Southeast Asia Scrapers
from scrapers.jobstreet_scraper import JobStreetScraper
from scrapers.jobsdb_scraper import JobsDBScraper
from scrapers.kalibrr_scraper import KalibrrScraper
from scrapers.jobthai_scraper import JobThaiScraper
from scrapers.vietnamworks_scraper import VietnamWorksScraper
from scrapers.glints_scraper import GlintsScraper
from scrapers.mycareersfuture_scraper import MyCareersFutureScraper

# East Asia Scrapers
from scrapers.fiftyonejob_scraper import FiftyOneJobScraper
from scrapers.zhaopin_scraper import ZhaopinScraper
from scrapers.bosszhipin_scraper import BossZhipinScraper
from scrapers.saramin_scraper import SaraminScraper
from scrapers.jobkorea_scraper import JobKoreaScraper
from scrapers.onezerofour_scraper import OneZeroFourScraper
from scrapers.doda_scraper import DodaScraper
from scrapers.mynavi_scraper import MynaviScraper

# Global / LinkedIn
from scrapers.linkedin_scraper import LinkedInScraper

logger = logging.getLogger(__name__)

ALL_SUPPORTED_BOARDS = [
    # Global / Professional
    "LinkedIn Jobs",
    "LinkedIn Posts",
    # MENA & Gulf (10)
    "Bayt.com",
    "GulfTalent",
    "Naukrigulf",
    "Wuzzuf",
    "Forasna",
    "Akhtaboot",
    "Tanqeeb",
    "ReKrute",
    "Emploitic",
    "Dubizzle",
    # South Asia (5)
    "Naukri",
    "Foundit",
    "Internshala",
    "Rozee",
    "Bdjobs",
    # Southeast Asia (7)
    "JobStreet",
    "JobsDB",
    "Kalibrr",
    "JobThai",
    "VietnamWorks",
    "Glints",
    "MyCareersFuture",
    # East Asia (8)
    "51job",
    "Zhaopin",
    "Boss Zhipin",
    "Saramin",
    "JobKorea",
    "104 Job Bank",
    "Doda",
    "Mynavi",
]


class MultiBoardJobScraper:
    """Orchestrates scraping across global and regional job boards across MENA,

    South Asia, Southeast Asia, and East Asia with strict 1-month date range filtering.
    """

    def __init__(self, request_delay: float = 1.0):
        # MENA
        self.bayt = BaytScraper(request_delay=request_delay)
        self.gulftalent = GulfTalentScraper(request_delay=request_delay)
        self.naukrigulf = NaukrigulfScraper(request_delay=request_delay)
        self.wuzzuf = WuzzufScraper(request_delay=request_delay)
        self.forasna = ForasnaScraper(request_delay=request_delay)
        self.akhtaboot = AkhtabootScraper(request_delay=request_delay)
        self.tanqeeb = TanqeebScraper(request_delay=request_delay)
        self.rekrute = ReKruteScraper(request_delay=request_delay)
        self.emploitic = EmploiticScraper(request_delay=request_delay)
        self.dubizzle = DubizzleScraper(request_delay=request_delay)

        # South Asia
        self.naukri = NaukriScraper(request_delay=request_delay)
        self.foundit = FounditScraper(request_delay=request_delay)
        self.internshala = InternshalaScraper(request_delay=request_delay)
        self.rozee = RozeeScraper(request_delay=request_delay)
        self.bdjobs = BdjobsScraper(request_delay=request_delay)

        # Southeast Asia
        self.jobstreet = JobStreetScraper(request_delay=request_delay)
        self.jobsdb = JobsDBScraper(request_delay=request_delay)
        self.kalibrr = KalibrrScraper(request_delay=request_delay)
        self.jobthai = JobThaiScraper(request_delay=request_delay)
        self.vietnamworks = VietnamWorksScraper(request_delay=request_delay)
        self.glints = GlintsScraper(request_delay=request_delay)
        self.mycareersfuture = MyCareersFutureScraper(request_delay=request_delay)

        # East Asia
        self.fiftyonejob = FiftyOneJobScraper(request_delay=request_delay)
        self.zhaopin = ZhaopinScraper(request_delay=request_delay)
        self.bosszhipin = BossZhipinScraper(request_delay=request_delay)
        self.saramin = SaraminScraper(request_delay=request_delay)
        self.jobkorea = JobKoreaScraper(request_delay=request_delay)
        self.onezerofour = OneZeroFourScraper(request_delay=request_delay)
        self.doda = DodaScraper(request_delay=request_delay)
        self.mynavi = MynaviScraper(request_delay=request_delay)

        # Global / LinkedIn
        self.linkedin = LinkedInScraper(request_delay=request_delay)

        self.db = JobDatabase()

    def scrape_all_boards(
        self,
        target_roles: list[str],
        search_keywords: list[str],
        negative_keywords: Optional[list[str]] = None,
        enabled_boards: Optional[list[str]] = None,
        max_days: int = 30,
    ) -> list[ScrapedJob]:
        """Runs scrapers across all target boards, filtering strictly for postings <= max_days (1 month)."""
        boards = enabled_boards or ALL_SUPPORTED_BOARDS
        negative_kws = [n.lower() for n in (negative_keywords or [])]

        # Formulate top search keywords
        primary_terms: list[str] = []
        for r in target_roles:
            if r and r not in primary_terms:
                primary_terms.append(r)
        for kw in search_keywords:
            if kw and kw not in primary_terms:
                primary_terms.append(kw)

        top_terms = primary_terms[:4] if primary_terms else ["Python", "Backend Developer"]
        logger.info(f"Starting Multi-Board Scraping with terms: {top_terms} on boards: {boards}")

        all_scraped: list[ScrapedJob] = []

        # ==========================================
        # 1. MENA & Gulf Boards
        # ==========================================
        if "Bayt.com" in boards:
            logger.info("--> Scraping Bayt.com (MENA & Gulf)...")
            try:
                bayt_jobs = self.bayt.scrape_by_keywords(
                    keywords=top_terms,
                    country="international",
                    max_jobs_per_keyword=8,
                    max_total_jobs=25,
                )
                all_scraped.extend(bayt_jobs)
                logger.info(f"Bayt.com returned {len(bayt_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Bayt.com scraping failed: {e}")

        if "GulfTalent" in boards:
            logger.info("--> Scraping GulfTalent.com (UAE & GCC)...")
            try:
                gt_jobs = self.gulftalent.scrape_category(category="software")
                all_scraped.extend(gt_jobs)
                logger.info(f"GulfTalent returned {len(gt_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"GulfTalent scraping failed: {e}")

        if "Naukrigulf" in boards:
            logger.info("--> Scraping Naukrigulf (GCC)...")
            try:
                ng_jobs = self.naukrigulf.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(ng_jobs)
                logger.info(f"Naukrigulf returned {len(ng_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Naukrigulf scraping failed: {e}")

        if "Wuzzuf" in boards:
            logger.info("--> Scraping Wuzzuf.net (Egypt)...")
            try:
                for term in top_terms[:2]:
                    wuzzuf_jobs = self.wuzzuf.scrape_keyword(keyword=term, max_pages=2)
                    all_scraped.extend(wuzzuf_jobs)
                logger.info(f"Wuzzuf returned {len(wuzzuf_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Wuzzuf scraping failed: {e}")

        if "Forasna" in boards:
            logger.info("--> Scraping Forasna (Egypt)...")
            try:
                forasna_jobs = self.forasna.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(forasna_jobs)
                logger.info(f"Forasna returned {len(forasna_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Forasna scraping failed: {e}")

        if "Akhtaboot" in boards:
            logger.info("--> Scraping Akhtaboot (Jordan & MENA)...")
            try:
                akhtaboot_jobs = self.akhtaboot.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(akhtaboot_jobs)
                logger.info(f"Akhtaboot returned {len(akhtaboot_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Akhtaboot scraping failed: {e}")

        if "Tanqeeb" in boards:
            logger.info("--> Scraping Tanqeeb.com (MENA Aggregator)...")
            try:
                tanqeeb_jobs = self.tanqeeb.scrape_keywords(
                    keywords=top_terms[:2],
                    countries=["egypt", "saudi"],
                )
                all_scraped.extend(tanqeeb_jobs)
                logger.info(f"Tanqeeb returned {len(tanqeeb_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Tanqeeb scraping failed: {e}")

        if "ReKrute" in boards:
            logger.info("--> Scraping ReKrute (Morocco)...")
            try:
                rekrute_jobs = self.rekrute.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(rekrute_jobs)
                logger.info(f"ReKrute returned {len(rekrute_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"ReKrute scraping failed: {e}")

        if "Emploitic" in boards:
            logger.info("--> Scraping Emploitic (Algeria)...")
            try:
                emploitic_jobs = self.emploitic.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(emploitic_jobs)
                logger.info(f"Emploitic returned {len(emploitic_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Emploitic scraping failed: {e}")

        if "Dubizzle" in boards:
            logger.info("--> Scraping Dubizzle (UAE & Egypt)...")
            try:
                dubizzle_jobs = self.dubizzle.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(dubizzle_jobs)
                logger.info(f"Dubizzle returned {len(dubizzle_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Dubizzle scraping failed: {e}")

        # ==========================================
        # 2. South Asia Boards
        # ==========================================
        if "Naukri" in boards:
            logger.info("--> Scraping Naukri (India)...")
            try:
                naukri_jobs = self.naukri.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(naukri_jobs)
                logger.info(f"Naukri returned {len(naukri_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Naukri scraping failed: {e}")

        if "Foundit" in boards:
            logger.info("--> Scraping Foundit (India & APAC)...")
            try:
                foundit_jobs = self.foundit.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(foundit_jobs)
                logger.info(f"Foundit returned {len(foundit_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Foundit scraping failed: {e}")

        if "Internshala" in boards:
            logger.info("--> Scraping Internshala (India)...")
            try:
                internshala_jobs = self.internshala.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(internshala_jobs)
                logger.info(f"Internshala returned {len(internshala_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Internshala scraping failed: {e}")

        if "Rozee" in boards:
            logger.info("--> Scraping Rozee.pk (Pakistan)...")
            try:
                rozee_jobs = self.rozee.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(rozee_jobs)
                logger.info(f"Rozee returned {len(rozee_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Rozee scraping failed: {e}")

        if "Bdjobs" in boards:
            logger.info("--> Scraping Bdjobs (Bangladesh)...")
            try:
                bd_jobs = self.bdjobs.scrape_keywords(keywords=top_terms[:3], max_jobs=20)
                all_scraped.extend(bd_jobs)
                logger.info(f"Bdjobs returned {len(bd_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Bdjobs scraping failed: {e}")

        # ==========================================
        # 3. Southeast Asia Boards
        # ==========================================
        if "JobStreet" in boards:
            logger.info("--> Scraping JobStreet (Southeast Asia)...")
            try:
                jobstreet_jobs = self.jobstreet.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(jobstreet_jobs)
                logger.info(f"JobStreet returned {len(jobstreet_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"JobStreet scraping failed: {e}")

        if "JobsDB" in boards:
            logger.info("--> Scraping JobsDB (Hong Kong, Thailand, Asia)...")
            try:
                jobsdb_jobs = self.jobsdb.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(jobsdb_jobs)
                logger.info(f"JobsDB returned {len(jobsdb_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"JobsDB scraping failed: {e}")

        if "Kalibrr" in boards:
            logger.info("--> Scraping Kalibrr (Southeast Asia)...")
            try:
                kalibrr_jobs = self.kalibrr.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(kalibrr_jobs)
                logger.info(f"Kalibrr returned {len(kalibrr_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Kalibrr scraping failed: {e}")

        if "JobThai" in boards:
            logger.info("--> Scraping JobThai (Thailand)...")
            try:
                jobthai_jobs = self.jobthai.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(jobthai_jobs)
                logger.info(f"JobThai returned {len(jobthai_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"JobThai scraping failed: {e}")

        if "VietnamWorks" in boards:
            logger.info("--> Scraping VietnamWorks (Vietnam)...")
            try:
                vn_jobs = self.vietnamworks.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(vn_jobs)
                logger.info(f"VietnamWorks returned {len(vn_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"VietnamWorks scraping failed: {e}")

        if "Glints" in boards:
            logger.info("--> Scraping Glints (Indonesia, Singapore, SEA)...")
            try:
                glints_jobs = self.glints.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(glints_jobs)
                logger.info(f"Glints returned {len(glints_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Glints scraping failed: {e}")

        if "MyCareersFuture" in boards:
            logger.info("--> Scraping MyCareersFuture (Singapore)...")
            try:
                mcf_jobs = self.mycareersfuture.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(mcf_jobs)
                logger.info(f"MyCareersFuture returned {len(mcf_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"MyCareersFuture scraping failed: {e}")

        # ==========================================
        # 4. East Asia Boards
        # ==========================================
        if "51job" in boards:
            logger.info("--> Scraping 51job (China)...")
            try:
                fiveone_jobs = self.fiftyonejob.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(fiveone_jobs)
                logger.info(f"51job returned {len(fiveone_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"51job scraping failed: {e}")

        if "Zhaopin" in boards:
            logger.info("--> Scraping Zhaopin (China)...")
            try:
                zhaopin_jobs = self.zhaopin.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(zhaopin_jobs)
                logger.info(f"Zhaopin returned {len(zhaopin_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Zhaopin scraping failed: {e}")

        if "Boss Zhipin" in boards:
            logger.info("--> Scraping BOSS Zhipin (China)...")
            try:
                boss_jobs = self.bosszhipin.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(boss_jobs)
                logger.info(f"BOSS Zhipin returned {len(boss_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"BOSS Zhipin scraping failed: {e}")

        if "Saramin" in boards:
            logger.info("--> Scraping Saramin (South Korea)...")
            try:
                saramin_jobs = self.saramin.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(saramin_jobs)
                logger.info(f"Saramin returned {len(saramin_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Saramin scraping failed: {e}")

        if "JobKorea" in boards:
            logger.info("--> Scraping JobKorea (South Korea)...")
            try:
                jobkorea_jobs = self.jobkorea.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(jobkorea_jobs)
                logger.info(f"JobKorea returned {len(jobkorea_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"JobKorea scraping failed: {e}")

        if "104 Job Bank" in boards:
            logger.info("--> Scraping 104 Job Bank (Taiwan)...")
            try:
                onezerofour_jobs = self.onezerofour.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(onezerofour_jobs)
                logger.info(f"104 Job Bank returned {len(onezerofour_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"104 Job Bank scraping failed: {e}")

        if "Doda" in boards:
            logger.info("--> Scraping Doda (Japan)...")
            try:
                doda_jobs = self.doda.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(doda_jobs)
                logger.info(f"Doda returned {len(doda_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Doda scraping failed: {e}")

        if "Mynavi" in boards:
            logger.info("--> Scraping Mynavi (Japan)...")
            try:
                mynavi_jobs = self.mynavi.scrape_keywords(keywords=top_terms[:2], max_jobs=20)
                all_scraped.extend(mynavi_jobs)
                logger.info(f"Mynavi returned {len(mynavi_jobs)} vacancies.")
            except Exception as e:
                logger.error(f"Mynavi scraping failed: {e}")

        # ==========================================
        # 5. Global & Professional (LinkedIn)
        # ==========================================
        if "LinkedIn Jobs" in boards or "LinkedIn" in boards:
            logger.info(f"--> Scraping LinkedIn Jobs (Global, <= {max_days} days old)...")
            try:
                li_jobs = self.linkedin.scrape_jobs(
                    keywords=top_terms[:2],
                    max_days=max_days,
                )
                all_scraped.extend(li_jobs)
                logger.info(f"LinkedIn Jobs returned {len(li_jobs)} vacancies within {max_days} days.")
            except Exception as e:
                logger.error(f"LinkedIn Jobs scraping failed: {e}")

        if "LinkedIn Posts" in boards or "LinkedIn" in boards:
            logger.info(f"--> Scraping LinkedIn Hiring Posts (Recruiter/Founder updates, <= {max_days} days old)...")
            try:
                li_posts = self.linkedin.scrape_posts(
                    keywords=top_terms[:2],
                    max_days=max_days,
                )
                all_scraped.extend(li_posts)
                logger.info(f"LinkedIn Posts returned {len(li_posts)} hiring posts within {max_days} days.")
            except Exception as e:
                logger.error(f"LinkedIn Posts scraping failed: {e}")

        # Apply negative keywords filter & deduplication
        filtered_jobs: list[ScrapedJob] = []
        seen_urls: set[str] = set()

        for job in all_scraped:
            if job.url in seen_urls:
                continue
            seen_urls.add(job.url)

            text_to_check = f"{job.title} {job.description_snippet}".lower()
            if any(neg in text_to_check for neg in negative_kws):
                logger.debug(f"Filtered out '{job.title}' by negative keyword.")
                continue

            filtered_jobs.append(job)

        # Save to SQLite
        new_count = self.db.save_jobs(filtered_jobs)
        logger.info(f"Saved {new_count} new vacancies into SQLite database ({len(filtered_jobs)} total in current batch).")

        return filtered_jobs
