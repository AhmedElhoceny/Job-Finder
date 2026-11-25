from typing import Optional
from pydantic import BaseModel, Field


class ScrapedJob(BaseModel):
    """Normalized schema for job postings scraped from platforms like Bayt.com."""

    id: str = Field(description="Unique identifier for the job posting (e.g. bayt_5510699)")
    title: str = Field(description="Job title")
    company: str = Field(description="Hiring company name")
    location: str = Field(description="Job location (city, country, or Remote)")
    career_level: Optional[str] = Field(default=None, description="Experience level (e.g. Mid Career, Senior Executive)")
    date_posted: Optional[str] = Field(default=None, description="Relative or absolute date posted")
    description_snippet: str = Field(default="", description="Snippet or full description text")
    url: str = Field(description="Direct URL to the job listing on the platform")
    source: str = Field(default="Bayt.com", description="Job board platform name")
    matched_keyword: Optional[str] = Field(default=None, description="The keyword or query that discovered this job")
