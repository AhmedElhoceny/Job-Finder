import json
import logging
from pathlib import Path
from typing import Any

from core.gemini_client import GeminiClient
from core.models.cv_analysis import CVAnalysisResult
from pipeline.state import CVPipelineState

logger = logging.getLogger(__name__)

GEMINI_SYNTHESIS_SYSTEM_PROMPT = """
You are an expert Technical Recruiter, ATS (Applicant Tracking System) Strategist, and Job Search Specialist.
Your task is to take the extracted candidate facts from the Hugging Face NuExtract model alongside the full CV text,
and synthesize the definitive list of Search Keywords and Search Queries that will be used by web scrapers to discover relevant job vacancies.

Critical Output Requirements:
1. 'search_keywords': Extract 10-15 high-signal keywords (technologies, core roles, concepts) that return high-relevance job postings.
2. 'search_queries': Formulate 5-8 ready-to-run search query strings combining role + core technology + remote/seniority (e.g., 'Senior Python Engineer remote', 'FastAPI Backend Developer').
3. 'target_roles': 3-5 best-matched job titles.
4. 'negative_keywords': Technologies, frameworks, and roles to strictly exclude (e.g. unrelated languages, junior/intern if senior).
5. 'core_skills' & 'secondary_skills': Categorized technical stack.
6. 'seniority_level' & 'estimated_years_of_experience': Objective assessment.
"""


def gemini_synthesizer_node(state: CVPipelineState) -> dict[str, Any]:
    """LangGraph Node 2: Takes NuExtract facts + CV text and uses Gemini Free LLM

    to synthesize the main search keywords and job search queries.
    """
    output_file = Path("data/cv_profile.json")
    force_reanalyze = state.get("force_reanalyze", False)

    # 1. Use cached profile if it already exists (saves Gemini API quota!)
    if output_file.exists() and not force_reanalyze:
        try:
            logger.info(f"[Node 2: Gemini] Using cached profile from {output_file.resolve()}...")
            result = CVAnalysisResult.model_validate_json(output_file.read_text(encoding="utf-8"))
            return {
                "cv_profile": result.model_dump(),
                "candidate_name": result.candidate_name,
                "seniority_level": result.seniority_level,
                "estimated_years_of_experience": result.estimated_years_of_experience,
                "target_roles": result.current_or_target_roles,
                "core_skills": result.core_skills,
                "secondary_skills": result.secondary_skills,
                "domains_and_industries": result.domains_and_industries,
                "search_keywords": result.search_keywords,
                "search_queries": result.search_queries,
                "negative_keywords": result.negative_keywords,
                "professional_summary": result.professional_summary,
                "current_stage": "keywords_synthesized",
                "status_messages": [
                    f"Node 2: Loaded {len(result.search_keywords)} cached search keywords "
                    f"and {len(result.search_queries)} search queries for '{result.candidate_name}'."
                ],
            }
        except Exception as e:
            logger.warning(f"Could not load cached profile ({e}), re-synthesizing with Gemini...")

    cv_text = state.get("cv_text", "")
    nuextract_data = state.get("nuextract_data")

    if not cv_text:
        return {
            "errors": ["No CV text available for Gemini synthesis."],
            "current_stage": "gemini_synthesis_failed",
        }

    logger.info("[Node 2: Gemini] Synthesizing search keywords and candidate strategy...")

    # Format NuExtract ground truth if available
    nuextract_context = ""
    if nuextract_data:
        nuextract_context = f"""
=== GROUND-TRUTH EXTRACTED BY Hugging Face NuExtract-tiny-Resume-Data-Extractor ===
Name: {nuextract_data.get('name')}
Email: {nuextract_data.get('email')}
Phone: {nuextract_data.get('phone')}
Website: {nuextract_data.get('website')}
Verified Skills: {', '.join(nuextract_data.get('skills', []))}
Work History: {json.dumps(nuextract_data.get('experience', []), indent=2)}
Education: {json.dumps(nuextract_data.get('education', []), indent=2)}
=== END NUEXTRACT DATA ===
"""

    prompt = f"""
Analyze the candidate's CV and the verified NuExtract ground-truth data to synthesize the Main Search Keywords and Queries:

{nuextract_context}

=== FULL CANDIDATE CV TEXT ===
{cv_text}
=== END CV TEXT ===

Instructions:
1. Verify candidate details, assessed seniority, and years of experience.
2. Formulate 3-5 high-demand target job roles.
3. Identify core skills and secondary skills.
4. Generate 10-15 high-precision SEARCH KEYWORDS for querying job platforms.
5. Generate 5-8 targeted SEARCH QUERY STRINGS for job boards.
6. Identify NEGATIVE KEYWORDS to exclude irrelevant listings.
7. Write a crisp 2-3 sentence professional summary.
"""

    gemini = GeminiClient()

    try:
        result: CVAnalysisResult = gemini.generate_structured(
            prompt=prompt,
            schema=CVAnalysisResult,
            system_instruction=GEMINI_SYNTHESIS_SYSTEM_PROMPT,
            temperature=0.1,
        )

        result.raw_text = cv_text
        if nuextract_data:
            from core.models.nuextract_schema import NuExtractResumeData
            result.nuextract_raw = NuExtractResumeData.model_validate(nuextract_data)

        # Save result to data/cv_profile.json
        output_file = Path("data/cv_profile.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"[Node 2: Gemini] Saved CV profile & keywords to {output_file.resolve()}")

        return {
            "cv_profile": result.model_dump(),
            "candidate_name": result.candidate_name,
            "seniority_level": result.seniority_level,
            "estimated_years_of_experience": result.estimated_years_of_experience,
            "target_roles": result.current_or_target_roles,
            "core_skills": result.core_skills,
            "secondary_skills": result.secondary_skills,
            "domains_and_industries": result.domains_and_industries,
            "search_keywords": result.search_keywords,
            "search_queries": result.search_queries,
            "negative_keywords": result.negative_keywords,
            "professional_summary": result.professional_summary,
            "current_stage": "keywords_synthesized",
            "status_messages": [
                f"Node 2 completed: Synthesized {len(result.search_keywords)} search keywords "
                f"and {len(result.search_queries)} search queries using Gemini."
            ],
        }

    except Exception as e:
        logger.error(f"[Node 2: Gemini] Failed to synthesize keywords: {e}")
        return {
            "errors": [f"Gemini keyword synthesis failed: {e}"],
            "current_stage": "gemini_synthesis_failed",
        }
