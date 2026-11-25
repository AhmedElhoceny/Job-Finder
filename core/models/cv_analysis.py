from typing import Optional
from pydantic import BaseModel, Field

from .nuextract_schema import NuExtractResumeData


class CVAnalysisResult(BaseModel):
    """Structured representation of parsed CV information and job search parameters."""

    candidate_name: str = Field(
        description="Full name of the candidate extracted from the CV"
    )
    contact_email: Optional[str] = Field(
        default=None, description="Email address found in CV"
    )
    contact_phone: Optional[str] = Field(
        default=None, description="Phone number found in CV"
    )
    location: Optional[str] = Field(
        default=None, description="Current city, country or geographic region"
    )
    seniority_level: str = Field(
        description="Assessed seniority level, e.g. Entry, Junior, Mid, Senior, Lead, Staff, Principal"
    )
    estimated_years_of_experience: float = Field(
        description="Calculated total years of professional experience"
    )
    current_or_target_roles: list[str] = Field(
        description="Target job titles suited for this candidate (e.g. ['Senior Backend Engineer', 'Python Developer', 'Full Stack Engineer'])"
    )
    core_skills: list[str] = Field(
        description="Top 5-10 primary technical skills, frameworks, and languages"
    )
    secondary_skills: list[str] = Field(
        description="Secondary technical tools, databases, cloud platforms, and methodologies"
    )
    domains_and_industries: list[str] = Field(
        default_factory=list,
        description="Industries or domains with proven experience (e.g. FinTech, SaaS, Healthcare, AI/ML)",
    )
    search_keywords: list[str] = Field(
        description="High-relevance individual keywords to use in job board search engines"
    )
    search_queries: list[str] = Field(
        description="Ready-to-use search query strings combining roles and key skills (e.g. ['Python Backend Developer remote', 'Senior FastAPI Engineer'])"
    )
    negative_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords and technologies to filter out because they don't match candidate experience or goals",
    )
    professional_summary: str = Field(
        description="2-3 sentence elevator pitch summarizing core competencies and impact"
    )
    nuextract_raw: Optional[NuExtractResumeData] = Field(
        default=None,
        description="Raw structured extraction directly from HuggingFace NuExtract-tiny model",
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Full raw text extracted from the CV document",
    )
