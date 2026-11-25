from typing import Annotated, Any, Optional
from typing_extensions import TypedDict


def merge_lists(left: list[Any], right: list[Any]) -> list[Any]:
    """Reducer that appends new items to an existing list in the state."""
    return (left or []) + (right or [])


class CVPipelineState(TypedDict, total=False):
    """The state flowing through the CV Processing and Keyword Extraction Pipeline."""

    # 1. Inputs
    cv_path: str
    skip_nuextract: bool
    enabled_boards: Optional[list[str]]

    # 2. Raw Text
    cv_text: str

    # 3. Node 1: Hugging Face NuExtract Extraction Output
    nuextract_data: Optional[dict[str, Any]]

    # 4. Node 2: Gemini Keyword & Search Strategy Synthesis Output
    candidate_name: str
    seniority_level: str
    estimated_years_of_experience: float
    target_roles: list[str]
    core_skills: list[str]
    secondary_skills: list[str]
    domains_and_industries: list[str]
    search_keywords: list[str]        # Main keywords to search jobs
    search_queries: list[str]         # Formatted query strings for job search bars
    negative_keywords: list[str]      # Keywords to exclude
    professional_summary: str
    cv_profile: Optional[dict[str, Any]]

    # 5. Node 3: Bayt Job Scraping Output
    discovered_jobs: list[dict[str, Any]]
    bayt_jobs: list[dict[str, Any]]

    # 6. Pipeline Telemetry
    current_stage: str
    status_messages: Annotated[list[str], merge_lists]
    errors: Annotated[list[str], merge_lists]
