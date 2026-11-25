import json
import logging
from pathlib import Path
from typing import Optional, Union

import docx
from pypdf import PdfReader

from config.settings import get_settings
from core.gemini_client import GeminiClient
from core.models.cv_analysis import CVAnalysisResult
from core.models.nuextract_schema import NuExtractResumeData
from core.nuextract_extractor import NuExtractResumeExtractor, get_extractor

logger = logging.getLogger(__name__)

CV_ANALYZER_SYSTEM_PROMPT = """
You are an expert Technical Recruiter, ATS (Applicant Tracking System) Specialist, and Job Search Strategist.
Your goal is to parse and deeply analyze a candidate's CV/Resume to extract actionable search parameters for an automated job application pipeline.

Focus on:
1. Identifying the candidate's exact level of seniority, target job titles, and strongest technical stack.
2. Generating precise, high-converting search keywords and queries that job search APIs (RemoteOK, Indeed, LinkedIn, Google Jobs) can use to find the best-matched vacancies.
3. Detecting negative keywords to prevent wasting time on irrelevant roles (e.g., unrelated languages, wrong seniority, technologies not in candidate's stack).
4. Crafting a crisp, high-impact professional summary.
"""


class CVAnalyzer:
    """Agent that ingests, parses, and extracts structured job search criteria from a CV."""

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        use_nuextract: bool = True,
    ):
        self.gemini_client = gemini_client or GeminiClient()
        self.use_nuextract = use_nuextract
        self._extractor: Optional[NuExtractResumeExtractor] = None

    @property
    def extractor(self) -> NuExtractResumeExtractor:
        if self._extractor is None:
            self._extractor = get_extractor()
        return self._extractor

    @staticmethod
    def extract_text(file_path: Union[str, Path]) -> str:
        """Extracts text content from PDF, DOCX, TXT, or Markdown files."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CV file not found: {path.resolve()}")

        suffix = path.suffix.lower()

        if suffix == ".pdf":
            reader = PdfReader(str(path))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            full_text = "\n".join(text_parts).strip()
            if not full_text:
                raise ValueError(f"Could not extract text from PDF: {path.name}. File may be scanned or empty.")
            return full_text

        elif suffix in (".docx", ".doc"):
            doc = docx.Document(str(path))
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()]).strip()
            if not full_text:
                raise ValueError(f"Could not extract text from Word document: {path.name}.")
            return full_text

        elif suffix in (".txt", ".md", ".markdown", ""):
            try:
                return path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                return path.read_text(encoding="latin-1").strip()

        else:
            raise ValueError(f"Unsupported CV file format '{suffix}'. Supported: .pdf, .docx, .txt, .md")

    def analyze_text(
        self,
        cv_text: str,
        skip_nuextract: bool = False,
    ) -> CVAnalysisResult:
        """Extracts structured candidate data and job search parameters from CV text.

        1. Runs nimendraai/NuExtract-tiny-Resume-Data-Extractor to pull verified facts.
        2. Passes extracted facts + CV to Gemini to synthesize optimal search queries and keywords.
        """
        if not cv_text or len(cv_text.strip()) < 50:
            raise ValueError("CV text is too short or empty to analyze.")

        nuextract_data: Optional[NuExtractResumeData] = None

        if self.use_nuextract and not skip_nuextract:
            try:
                logger.info("Running Hugging Face NuExtract-tiny-Resume-Data-Extractor...")
                nuextract_data = self.extractor.extract(cv_text)
                logger.info(
                    f"NuExtract successfully parsed candidate: '{nuextract_data.name}' "
                    f"with {len(nuextract_data.skills)} skills and {len(nuextract_data.experience)} experiences"
                )
            except Exception as e:
                logger.warning(f"NuExtract extraction failed ({e}), falling back directly to Gemini synthesizer.")

        # Build synthesis prompt combining raw CV text and NuExtract's ground-truth extraction
        nuextract_context = ""
        if nuextract_data:
            nuextract_context = f"""
=== GROUND-TRUTH EXTRACTED BY NuExtract-tiny-Resume-Data-Extractor ===
Name: {nuextract_data.name}
Email: {nuextract_data.email}
Phone: {nuextract_data.phone}
Website: {nuextract_data.website}
Verified Skills: {', '.join(nuextract_data.skills)}
Experience: {[e.model_dump() for e in nuextract_data.experience]}
Education: {[e.model_dump() for e in nuextract_data.education]}
Other Details: {nuextract_data.other_details}
=== END NUEXTRACT DATA ===
"""

        prompt = f"""
Please analyze the following Candidate CV and ground-truth extracted data to synthesize structured job search attributes:

{nuextract_context}

=== ORIGINAL CV TEXT ===
{cv_text}
=== END ORIGINAL CV TEXT ===

Instructions:
1. Accurately verify the candidate's name, email, phone, and location.
2. Calculate total professional experience and assess realistic seniority level (e.g. Mid, Senior, Lead).
3. Target Roles: Provide 3-5 high-demand job titles suited for this candidate (e.g. 'Senior Python Backend Developer', 'Cloud Engineer').
4. Core Skills: Synthesize the 5-10 primary technical skills, prioritizing those with deepest experience.
5. Secondary Skills: List secondary tools, frameworks, databases, and DevOps utilities.
6. Domains & Industries: Identify industry domains (e.g. FinTech, SaaS, AI, HealthTech).
7. Search Keywords: 10-15 high-signal keywords for job search engines.
8. Search Queries: 5-8 ready-to-run job search strings optimized for job boards (e.g. 'Python Backend Engineer remote', 'Senior FastAPI Developer').
9. Negative Keywords: Technologies or roles to exclude (e.g. non-matching stacks like PHP, WordPress, or Junior/Intern).
10. Professional Summary: 2-3 sentence impactful executive summary.
"""

        result: CVAnalysisResult = self.gemini_client.generate_structured(
            prompt=prompt,
            schema=CVAnalysisResult,
            system_instruction=CV_ANALYZER_SYSTEM_PROMPT,
            temperature=0.1,
        )

        result.nuextract_raw = nuextract_data
        result.raw_text = cv_text
        return result

    def analyze_file(
        self,
        file_path: Union[str, Path],
        output_json_path: Optional[Union[str, Path]] = None,
        skip_nuextract: bool = False,
    ) -> CVAnalysisResult:
        """Extracts text from a file, runs NuExtract + Gemini analysis, and saves the profile."""
        logger.info(f"Extracting text from CV: {file_path}")
        text = self.extract_text(file_path)

        logger.info("Analyzing CV...")
        result = self.analyze_text(text, skip_nuextract=skip_nuextract)

        if output_json_path:
            self.save_profile(result, output_json_path)

        return result

    @staticmethod
    def save_profile(result: CVAnalysisResult, output_path: Union[str, Path]) -> Path:
        """Saves the CV analysis result to a JSON file."""
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"Saved CV profile to: {target.resolve()}")
        return target

    @staticmethod
    def load_profile(input_path: Union[str, Path]) -> CVAnalysisResult:
        """Loads a previously saved CV analysis result from a JSON file."""
        target = Path(input_path)
        if not target.exists():
            raise FileNotFoundError(f"CV profile not found at: {target.resolve()}")
        return CVAnalysisResult.model_validate_json(target.read_text(encoding="utf-8"))
