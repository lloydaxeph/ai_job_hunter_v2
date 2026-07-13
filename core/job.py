from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from core.constants import JobStatus


@dataclass
class Job:
    title: str
    company: str
    url: str
    site: str
    score: int = 0
    description: str = ""
    resume_used: str = "NA"
    date: datetime = field(default_factory=datetime.now)
    status: JobStatus = JobStatus.FOUND

    @property
    def job_id(self) -> str:
        title = self.title.lower().strip().replace(" ", "-")
        company = self.company.lower().strip().replace(" ", "-")
        return f"{title}_{company}"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["job_id"] = self.job_id
        data["status"] = str(self.status)
        return data
