# MENA & Gulf
from .bayt_scraper import BaytScraper
from .gulftalent_scraper import GulfTalentScraper
from .naukrigulf_scraper import NaukrigulfScraper
from .wuzzuf_scraper import WuzzufScraper
from .wuzzuf_applier import WuzzufApplier
from .forasna_scraper import ForasnaScraper
from .akhtaboot_scraper import AkhtabootScraper
from .tanqeeb_scraper import TanqeebScraper
from .rekrute_scraper import ReKruteScraper
from .emploitic_scraper import EmploiticScraper
from .dubizzle_scraper import DubizzleScraper

# South Asia
from .naukri_scraper import NaukriScraper
from .foundit_scraper import FounditScraper
from .internshala_scraper import InternshalaScraper
from .rozee_scraper import RozeeScraper
from .bdjobs_scraper import BdjobsScraper

# Southeast Asia
from .jobstreet_scraper import JobStreetScraper
from .jobsdb_scraper import JobsDBScraper
from .kalibrr_scraper import KalibrrScraper
from .jobthai_scraper import JobThaiScraper
from .vietnamworks_scraper import VietnamWorksScraper
from .glints_scraper import GlintsScraper
from .mycareersfuture_scraper import MyCareersFutureScraper

# East Asia
from .fiftyonejob_scraper import FiftyOneJobScraper
from .zhaopin_scraper import ZhaopinScraper
from .bosszhipin_scraper import BossZhipinScraper
from .saramin_scraper import SaraminScraper
from .jobkorea_scraper import JobKoreaScraper
from .onezerofour_scraper import OneZeroFourScraper
from .doda_scraper import DodaScraper
from .mynavi_scraper import MynaviScraper

# Global / Professional
from .linkedin_jobs_scraper import LinkedInJobsScraper
from .linkedin_posts_scraper import LinkedInPostsScraper
from .linkedin_scraper import LinkedInScraper

from .aggregator import MultiBoardJobScraper, ALL_SUPPORTED_BOARDS

__all__ = [
    # MENA
    "BaytScraper",
    "GulfTalentScraper",
    "NaukrigulfScraper",
    "WuzzufScraper",
    "WuzzufApplier",
    "ForasnaScraper",
    "AkhtabootScraper",
    "TanqeebScraper",
    "ReKruteScraper",
    "EmploiticScraper",
    "DubizzleScraper",
    # South Asia
    "NaukriScraper",
    "FounditScraper",
    "InternshalaScraper",
    "RozeeScraper",
    "BdjobsScraper",
    # Southeast Asia
    "JobStreetScraper",
    "JobsDBScraper",
    "KalibrrScraper",
    "JobThaiScraper",
    "VietnamWorksScraper",
    "GlintsScraper",
    "MyCareersFutureScraper",
    # East Asia
    "FiftyOneJobScraper",
    "ZhaopinScraper",
    "BossZhipinScraper",
    "SaraminScraper",
    "JobKoreaScraper",
    "OneZeroFourScraper",
    "DodaScraper",
    "MynaviScraper",
    # LinkedIn
    "LinkedInJobsScraper",
    "LinkedInPostsScraper",
    "LinkedInScraper",
    # Aggregator
    "MultiBoardJobScraper",
    "ALL_SUPPORTED_BOARDS",
]
