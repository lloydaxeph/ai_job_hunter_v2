from __future__ import annotations

import json

from openai import OpenAI

from ai.prompts import form_answer_prompt, score_job_prompt
from core.config import AppConfig
from core.logging import AppLogger


class AIClient:
    """Wraps the OpenAI chat-completions API for scoring and form Q&A."""

    def __init__(self, cfg: AppConfig):
        if not cfg.credentials.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )

        self.cfg = cfg
        self.client = OpenAI(api_key=cfg.credentials.openai_api_key)
        self.console = AppLogger.console()
        self.logger = AppLogger.logger()

    def answer_application_questions(self, questions: list[dict]) -> list[dict]:
        prompt = form_answer_prompt(self.cfg.about_me, questions)

        response = self.client.chat.completions.create(
            model=self.cfg.ai.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()

        try:
            return json.loads(raw)["answers"]
        except Exception as e:
            raise RuntimeError(f"Failed parsing AI response:\n{raw}") from e

    def score_job(self, job: dict) -> dict:
        """Ask GPT to score relevance 1-10 and recommend a resume."""
        resume_files = self.cfg.resume_files()
        prompt = score_job_prompt(self.cfg.ai, job, resume_files)

        response = self.client.chat.completions.create(
            model=self.cfg.ai.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()

        try:
            result = json.loads(raw)
        except Exception as e:
            self.console.print(f"[red]JSON parse error: {e}[/red]")
            self.console.print(f"[yellow]Raw response: {raw}[/yellow]")
            self.logger.warning("score_job JSON parse error: %s", e)
            return {
                "score": 0,
                "reason": "parse error",
                "missing": [],
                "recommended_resume": None,
            }

        if result.get("recommended_resume") not in resume_files:
            result["recommended_resume"] = None

        return result
