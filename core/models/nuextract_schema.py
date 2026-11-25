from typing import Optional
from pydantic import BaseModel, Field


class NuExtractExperience(BaseModel):
    title: Optional[str] = ""
    company: Optional[str] = ""
    duration: Optional[str] = ""


class NuExtractEducation(BaseModel):
    degree: Optional[str] = ""
    institution: Optional[str] = ""
    year: Optional[str] = ""


class NuExtractResumeData(BaseModel):
    """Schema matched to nimendraai/NuExtract-tiny-Resume-Data-Extractor."""

    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    experience: list[NuExtractExperience] = Field(default_factory=list)
    education: list[NuExtractEducation] = Field(default_factory=list)
    other_details: list[str] = Field(default_factory=list)
