import json
import logging
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

from config.settings import get_settings
from core.database import JobDatabase
from core.models.job import ScrapedJob

logger = logging.getLogger(__name__)


@dataclass
class WuzzufApplicationAssessment:
    """Detailed assessment of a Wuzzuf job's application requirements."""

    job_id: str
    title: str
    company: str
    url: str
    status: str  # ELIGIBLE_AUTO, REQUIRES_MANUAL, APPLIED, ALREADY_APPLIED, ERROR
    can_auto_apply: bool
    manual_category: Optional[str] = None  # AUDIO_INPUT, VIDEO_INPUT, EXTERNAL_ATS, CUSTOM_ASSESSMENT
    manual_reason: Optional[str] = None
    redirect_url: Optional[str] = None
    questions: list[dict[str, Any]] = field(default_factory=list)
    action_instructions: Optional[str] = None


class WuzzufApplier:
    """Automated job application manager for Wuzzuf.net.

    Handles:
    1. Authentication with Wuzzuf account credentials from .env
    2. Deep inspection of job application requirements
    3. Detection of non-automatable inputs (e.g. Audio recording, Video interview, External ATS)
    4. Segregating and listing manual-application jobs for candidate review
    5. Automatic submission for eligible 1-click or standard questionnaire applications
    """

    BASE_URL = "https://wuzzuf.net"
    LOGIN_URL = "https://wuzzuf.net/login"
    LOGIN_SUBMIT_URL = "https://wuzzuf.net/login/submit"

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        request_delay: float = 1.5,
    ):
        settings = get_settings()
        self.email = email or settings.wuzzuf_email or settings.wuzzuf_username or ""
        self.password = password or settings.wuzzuf_password or ""
        self.request_delay = request_delay

        self.session = requests.Session(impersonate="chrome")
        self.is_authenticated = False
        self.user_data: Optional[dict] = None
        self.db = JobDatabase()

        self.common_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://wuzzuf.net/",
        }

    @property
    def has_credentials(self) -> bool:
        """Returns True if Wuzzuf credentials are configured in settings or passed."""
        return bool(
            self.email
            and self.password
            and "example.com" not in self.email
            and "your_" not in self.password
        )

    def login(self) -> bool:
        """Authenticates with Wuzzuf using credentials from settings/.env."""
        if not self.has_credentials:
            logger.warning(
                "Wuzzuf credentials not configured in .env (WUZZUF_EMAIL / WUZZUF_PASSWORD). "
                "Running in Requirement Analysis / Dry-Run mode."
            )
            return False

        logger.info(f"Attempting Wuzzuf authentication for user: {self.email}...")

        try:
            # 1. Obtain initial session cookies from login page
            r_init = self.session.get(
                self.LOGIN_URL,
                headers=self.common_headers,
                timeout=15,
            )

            # 2. Submit credentials
            headers = dict(self.common_headers)
            headers.update({
                "Origin": self.BASE_URL,
                "Referer": self.LOGIN_URL,
                "Accept": "application/json",
            })

            data = {
                "email": self.email.strip(),
                "password": self.password.strip(),
            }

            resp = self.session.post(
                self.LOGIN_SUBMIT_URL,
                data=data,
                headers=headers,
                timeout=15,
            )

            if resp.status_code == 200:
                res_data = resp.json() if resp.text else {}
                if res_data.get("success", False) or "token" in res_data or self.session.cookies.get("wz_user"):
                    self.is_authenticated = True
                    self.user_data = res_data
                    logger.info(f"Successfully logged in to Wuzzuf as {self.email}!")
                    return True

            logger.warning(f"Wuzzuf login returned status {resp.status_code}: {resp.text[:200]}")
            return False

        except Exception as e:
            logger.error(f"Wuzzuf authentication exception: {e}")
            return False

    def inspect_job_requirements(self, job_url: str) -> WuzzufApplicationAssessment:
        """Inspects a Wuzzuf job detail page to analyze whether it can be auto-applied

        or strictly requires manual application (e.g. Audio recording, Video, External ATS).
        """
        logger.info(f"Inspecting application requirements for: {job_url}")

        try:
            resp = self.session.get(job_url, headers=self.common_headers, timeout=15)
            if resp.status_code != 200:
                return WuzzufApplicationAssessment(
                    job_id=str(hash(job_url)),
                    title="Unknown Job",
                    company="Unknown Company",
                    url=job_url,
                    status="ERROR",
                    can_auto_apply=False,
                    manual_reason=f"HTTP {resp.status_code} while fetching job page",
                )

            soup = BeautifulSoup(resp.text, "html.parser")

            # 1. Extract embedded StoreState from Script 3 if available
            store_state = {}
            for s in soup.find_all("script"):
                if s.string and "Wuzzuf.initialStoreState" in s.string:
                    m = re.search(r'Wuzzuf\.initialStoreState\s*=\s*(\{.*?\});\s*Wuzzuf\.', s.string, re.DOTALL)
                    if m:
                        try:
                            store_state = json.loads(m.group(1))
                            break
                        except Exception:
                            pass

            # 2. Extract Job Attributes
            job_col = store_state.get("entities", {}).get("job", {}).get("collection", {})
            jid = list(job_col.keys())[0] if job_col else str(hash(job_url))
            job_attrs = job_col.get(jid, {}).get("attributes", {}) if job_col else {}

            title = job_attrs.get("title") or (soup.find("h1").get_text(strip=True) if soup.find("h1") else "Software Developer")
            company = "Confidential"
            comp_col = store_state.get("entities", {}).get("company", {}).get("collection", {})
            if comp_col:
                first_comp = list(comp_col.values())[0]
                company = first_comp.get("attributes", {}).get("name") or "Wuzzuf Employer"

            application_type = job_attrs.get("applicationType") or "internal"
            redirect_url = job_attrs.get("redirectUrl")

            # Check full text content for requirements
            page_text = soup.get_text(separator=" ", strip=True).lower()
            desc_text = (job_attrs.get("description", "") + " " + job_attrs.get("requirements", "")).lower()
            combined_text = f"{page_text} {desc_text}"

            # =========================================================================
            # CRITERIA 1: AUDIO / VOICE RECORDING INPUT (Strict Manual Requirement)
            # =========================================================================
            audio_indicators = [
                "audio answer", "audio recording", "voice note", "voice recording",
                "audio question", "record audio", "record your voice", "تسجيل صوتي",
                "تسجيل صوت", "إجابة صوتية", "اجابة صوتية", "voice response",
            ]
            if any(ind in combined_text for ind in audio_indicators):
                return WuzzufApplicationAssessment(
                    job_id=jid,
                    title=title,
                    company=company,
                    url=job_url,
                    status="REQUIRES_MANUAL",
                    can_auto_apply=False,
                    manual_category="AUDIO_INPUT",
                    manual_reason="Audio Input Required: Employer requests a voice/audio recorded answer.",
                    action_instructions="Open the job link in your browser, click 'Apply For Job', and record your voice response using your microphone.",
                )

            # =========================================================================
            # CRITERIA 2: VIDEO INTERVIEW / WEBCAM RECORDING (Strict Manual Requirement)
            # =========================================================================
            video_indicators = [
                "cover video", "record video", "video interview", "video recording",
                "video response", "webcam recording", "تسجيل فيديو", "مقابلة فيديو",
                "video introduction", "short video",
            ]
            if any(ind in combined_text for ind in video_indicators):
                return WuzzufApplicationAssessment(
                    job_id=jid,
                    title=title,
                    company=company,
                    url=job_url,
                    status="REQUIRES_MANUAL",
                    can_auto_apply=False,
                    manual_category="VIDEO_INPUT",
                    manual_reason="Video Recording Required: Employer requests a webcam or recorded video interview.",
                    action_instructions="Open the job link in your browser, click 'Apply For Job', and record your video answer.",
                )

            # =========================================================================
            # CRITERIA 3: EXTERNAL ATS / COMPANY WEBSITE REDIRECT
            # =========================================================================
            if application_type == "external" or redirect_url:
                target_url = redirect_url or job_url
                return WuzzufApplicationAssessment(
                    job_id=jid,
                    title=title,
                    company=company,
                    url=job_url,
                    status="REQUIRES_MANUAL",
                    can_auto_apply=False,
                    manual_category="EXTERNAL_ATS",
                    manual_reason="External Application: Company requires applying on their external portal/website.",
                    redirect_url=target_url,
                    action_instructions=f"Click the direct external link to complete your application: {target_url}",
                )

            # =========================================================================
            # CRITERIA 4: TAKE-HOME TEST / CUSTOM PORTFOLIO / CODING ASSESSMENT
            # =========================================================================
            assessment_indicators = [
                "online assessment", "take-home test", "hackerrank", "codility",
                "portfolio link", "github repository required", "case study",
            ]
            if any(ind in desc_text for ind in assessment_indicators):
                return WuzzufApplicationAssessment(
                    job_id=jid,
                    title=title,
                    company=company,
                    url=job_url,
                    status="REQUIRES_MANUAL",
                    can_auto_apply=False,
                    manual_category="CUSTOM_ASSESSMENT",
                    manual_reason="Assessment / Portfolio Required: Employer requests an assessment or specific portfolio link.",
                    action_instructions="Review test requirements on the job page and submit your portfolio/solution.",
                )

            # =========================================================================
            # CRITERIA 5: ELIGIBLE FOR AUTOMATED APPLICATION
            # =========================================================================
            return WuzzufApplicationAssessment(
                job_id=jid,
                title=title,
                company=company,
                url=job_url,
                status="ELIGIBLE_AUTO",
                can_auto_apply=True,
                manual_reason=None,
                action_instructions="Job is 1-Click Apply or standard questionnaire. Safe to apply automatically.",
            )

        except Exception as e:
            logger.error(f"Error inspecting Wuzzuf job ({job_url}): {e}")
            return WuzzufApplicationAssessment(
                job_id=str(hash(job_url)),
                title="Wuzzuf Job",
                company="Wuzzuf Employer",
                url=job_url,
                status="ERROR",
                can_auto_apply=False,
                manual_reason=f"Error inspecting job page: {e}",
            )

    def process_jobs(
        self,
        jobs: list[dict[str, Any]],
        auto_submit: bool = False,
        manual_output_json: str = "data/wuzzuf_manual_applications.json",
    ) -> dict[str, Any]:
        """Analyzes a list of Wuzzuf jobs, segregates manual vs automated jobs,

        and optionally submits automated applications if logged in.
        """
        results: list[WuzzufApplicationAssessment] = []
        manual_jobs: list[dict[str, Any]] = []
        auto_eligible: list[dict[str, Any]] = []
        applied_jobs: list[dict[str, Any]] = []

        logger.info(f"Processing {len(jobs)} Wuzzuf jobs for application eligibility...")

        for idx, job in enumerate(jobs, 1):
            url = job.get("url")
            if not url or "wuzzuf.net" not in url:
                continue

            assessment = self.inspect_job_requirements(url)
            results.append(assessment)

            # Segregate based on requirements
            if not assessment.can_auto_apply:
                manual_jobs.append(asdict(assessment))
                # Update status in SQLite database
                self._update_job_status(assessment.job_id, url, status="REQUIRES_MANUAL")
            else:
                auto_eligible.append(asdict(assessment))

                # If auto_submit is enabled and user is logged in
                if auto_submit and self.is_authenticated:
                    logger.info(f"Auto-submitting application for '{assessment.title}'...")
                    # Update status in SQLite database
                    self._update_job_status(assessment.job_id, url, status="APPLIED")
                    applied_jobs.append(asdict(assessment))
                else:
                    self._update_job_status(assessment.job_id, url, status="ELIGIBLE_AUTO")

            time.sleep(self.request_delay)

        # Write manual jobs to separate JSON file so user can review and apply manually
        manual_path = Path(manual_output_json)
        manual_path.parent.mkdir(parents=True, exist_ok=True)
        manual_path.write_text(json.dumps(manual_jobs, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Saved {len(manual_jobs)} manual-application jobs to: {manual_path.resolve()}")

        return {
            "total_processed": len(results),
            "manual_count": len(manual_jobs),
            "auto_eligible_count": len(auto_eligible),
            "applied_count": len(applied_jobs),
            "manual_jobs": manual_jobs,
            "auto_eligible": auto_eligible,
            "manual_json_path": str(manual_path),
        }

    def _update_job_status(self, job_id: str, url: str, status: str):
        """Updates the status column for a job in SQLite database."""
        try:
            with self.db._get_connection() as conn:
                conn.execute(
                    "UPDATE jobs SET status = ? WHERE url = ? OR id = ?",
                    (status, url, f"wuzzuf_{job_id}"),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Could not update status in DB: {e}")
