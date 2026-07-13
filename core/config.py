from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class SearchConfig(BaseModel):
    keywords: list[str]
    locations: list[str]
    max_results_per_site: int = 10
    sites: list[str]


class ResumeRule(BaseModel):
    file: str
    use_when: list[str] | None = None


class WorkExperienceEntry(BaseModel):
    title: str
    company: str
    duration: str
    details: str = ""


class EducationEntry(BaseModel):
    degree: str
    school: str
    year: str = ""


class AIConfig(BaseModel):
    model: str
    years_experience: int = 0
    score_threshold: int = 7
    personal_summary: str = ""
    work_experience: list[WorkExperienceEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


class BannedConfig(BaseModel):
    companies: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)


class PersonalConfig(BaseModel):
    first_name: str = ""
    last_name: str = ""
    middle_name: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    work_auth: str = ""


class ApplyConfig(BaseModel):
    auto_apply: bool = True
    delay_between_apps: float = 3.0
    delay_min: float | None = None
    delay_max: float | None = None
    max_apps_per_run: int = 100
    headless: bool = False

    def jitter_bounds(self) -> tuple[float, float]:
        """Return (min, max) delay seconds, falling back to the fixed delay."""
        if self.delay_min is not None and self.delay_max is not None:
            return self.delay_min, self.delay_max
        return self.delay_between_apps, self.delay_between_apps


class Credentials(BaseModel):
    linkedin_email: str = ""
    linkedin_password: str = ""
    jobstreet_email: str = ""
    jobstreet_password: str = ""
    xing_email: str = ""
    xing_password: str = ""
    openai_api_key: str = ""


class AppConfig(BaseModel):
    search: SearchConfig
    resumes: list[ResumeRule]
    ai: AIConfig
    banned: BannedConfig = Field(default_factory=BannedConfig)
    personal: PersonalConfig = Field(default_factory=PersonalConfig)
    apply: ApplyConfig = Field(default_factory=ApplyConfig)
    about_me: str = ""
    credentials: Credentials = Field(default_factory=Credentials)

    @property
    def banned_companies(self) -> list[str]:
        return [c.lower() for c in self.banned.companies]

    @property
    def banned_titles(self) -> list[str]:
        return [t.lower() for t in self.banned.titles]

    def pick_resume(self, job_title: str) -> str:
        """Keyword-overlap fallback resume picker.

        Superseded in the normal flow by AIClient.score_job()'s resume
        recommendation, which sees the full job description. This remains
        as a fallback if the AI does not return a usable recommendation.
        """
        if not self.resumes:
            raise ValueError("No resumes configured.")

        title = job_title.lower()
        default_resume: str | None = None
        best_resume: str | None = None
        best_score = 0

        for resume in self.resumes:
            if not resume.use_when:
                default_resume = resume.file
                continue

            score = sum(keyword.lower() in title for keyword in resume.use_when)
            if score > best_score:
                best_score = score
                best_resume = resume.file

        return best_resume or default_resume or self.resumes[0].file

    def resume_files(self) -> list[str]:
        return [resume.file for resume in self.resumes]

    @classmethod
    def load(cls, config_path: str | Path = "config.yaml") -> "AppConfig":
        with open(config_path, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f)

        raw["credentials"] = {
            "linkedin_email": os.getenv("LINKEDIN_EMAIL", ""),
            "linkedin_password": os.getenv("LINKEDIN_PASSWORD", ""),
            "jobstreet_email": os.getenv("JOBSTREET_EMAIL", ""),
            "jobstreet_password": os.getenv("JOBSTREET_PASSWORD", ""),
            "xing_email": os.getenv("XING_EMAIL", ""),
            "xing_password": os.getenv("XING_PASSWORD", ""),
            "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        }

        return cls.model_validate(raw)
