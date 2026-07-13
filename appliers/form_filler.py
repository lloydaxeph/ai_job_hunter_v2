from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Locator

from ai.openai_client import AIClient
from core.logging import AppLogger

# Shared across LinkedIn and JobStreet — v1 had this exact 45-keyword set
# copy-pasted verbatim in both Appliers/LinkedIn.py and Appliers/JobStreet.py.
TECHNICAL_KEYWORDS = {
    "software", "developer", "development", "programming", "coding", "engineer",
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "computer vision", "data science", "python", "java", "c#", "c++",
    "javascript", "typescript", "react", "angular", "vue", "django", "flask",
    "fastapi", ".net", "dotnet", "sql", "mongodb", "mysql", "postgres", "aws",
    "azure", "gcp", "docker", "kubernetes", "git", "github", "linux", "api",
    "backend", "frontend", "full stack", "devops", "cloud", "sponsorship",
    "authorized to work", "work authorization",
}


@dataclass
class Question:
    id: str
    type: str  # "text" | "select" | "radio"
    question: str
    choices: list[str] | None = None


class FormFiller:
    """Discovers unanswered text/select/radio fields within a scope locator,
    asks the AI to answer them, and fills the answers back into the DOM.

    This is the logic that was ~90% duplicated between v1's
    Appliers/LinkedIn.py and Appliers/JobStreet.py `fill_form` methods.
    Site differences (whether textareas count as text fields, how a
    "no answer selected" select option reads, how radios get clicked) are
    passed in as constructor flags rather than duplicated per subclass.
    """

    def __init__(
        self,
        ai_client: AIClient,
        include_textarea: bool = False,
        empty_select_labels: tuple[str, ...] = ("select an option",),
    ):
        self.ai_client = ai_client
        self.include_textarea = include_textarea
        self.empty_select_labels = {label.lower() for label in empty_select_labels}
        self.console = AppLogger.console()
        self.app = "[Applier]"

    def fill(self, scope: Locator, confidence_threshold: int = 90) -> bool:
        """Fill every unanswered field within `scope`. Returns False if any
        answer's confidence is below `confidence_threshold` (caller should
        stop and route the job to manual review)."""
        questions: list[Question] = []
        field_map: dict[str, Locator] = {}

        self._discover_text_fields(scope, questions, field_map)
        self._discover_select_fields(scope, questions, field_map)
        self._discover_radio_fields(scope, questions, field_map)

        if not questions:
            return True

        self.console.print(f"[cyan]{self.app} Answering {len(questions)} form question(s) via AI...[/cyan]")

        answers = self.ai_client.answer_application_questions(
            [q.__dict__ for q in questions]
        )
        question_lookup = {q.id: q.question for q in questions}
        type_lookup = {q.id: q.type for q in questions}

        for answer in answers:
            if answer["confidence"] < confidence_threshold:
                self.console.print(
                    f"[red]{self.app} Confidence too low ({answer['confidence']}%) "
                    f"for question '{answer['id']}' — halting form fill.[/red]"
                )
                return False

            field = field_map[answer["id"]]
            field_type = type_lookup[answer["id"]]
            value = str(answer["answer"]).strip()

            self._apply_answer(field, field_type, value)

            self.console.print(
                f"[cyan]{self.app} Answered:[/cyan] {value} "
                f"[dim]({question_lookup.get(answer['id'], '')})[/dim]"
            )

        self.console.print(f"[green]{self.app} Form fill complete.[/green]")
        return True

    # ------------------------------------------------------------------ #
    # Field discovery
    # ------------------------------------------------------------------ #
    def _discover_text_fields(self, scope: Locator, questions: list[Question], field_map: dict[str, Locator]) -> None:
        selector = "input[type='text'], input[type='number']"
        if self.include_textarea:
            selector += ", textarea"

        fields = scope.locator(selector)
        for i in range(fields.count()):
            field = fields.nth(i)
            try:
                if not field.is_visible():
                    continue

                field_id = field.get_attribute("id")
                if not field_id:
                    continue

                if (field.input_value() or "").strip():
                    continue

                label = scope.locator(f"label[for='{field_id}']").first
                question_text = (label.inner_text() or "").strip()
                if not question_text:
                    continue

                questions.append(Question(id=field_id, type="text", question=question_text))
                field_map[field_id] = field

            except Exception:
                continue

    def _discover_select_fields(self, scope: Locator, questions: list[Question], field_map: dict[str, Locator]) -> None:
        selects = scope.locator("select")
        for i in range(selects.count()):
            select = selects.nth(i)
            try:
                if not select.is_visible():
                    continue

                select_id = select.get_attribute("id")
                if not select_id:
                    continue

                current_value = (select.input_value() or "").strip()
                if current_value and current_value.lower() not in self.empty_select_labels:
                    continue

                label = scope.locator(f"label[for='{select_id}']").first
                question_text = (label.inner_text() or "").strip()
                if not question_text:
                    continue

                options = []
                option_nodes = select.locator("option")
                for j in range(option_nodes.count()):
                    text = option_nodes.nth(j).inner_text().strip()
                    if not text or text.lower().startswith("select"):
                        continue
                    options.append(text)

                questions.append(Question(id=select_id, type="select", question=question_text, choices=options))
                field_map[select_id] = select

            except Exception:
                continue

    def _discover_radio_fields(self, scope: Locator, questions: list[Question], field_map: dict[str, Locator]) -> None:
        fieldsets = scope.locator("fieldset")
        for i in range(fieldsets.count()):
            fieldset = fieldsets.nth(i)
            try:
                legend = (
                    fieldset.locator("legend, .fb-dash-form-element__label").first.inner_text().strip()
                )
                if not legend:
                    continue

                radios = fieldset.locator("input[type='radio']")

                already_answered = False
                for j in range(radios.count()):
                    if radios.nth(j).is_checked():
                        already_answered = True
                        break
                if already_answered:
                    continue

                choices = []
                for j in range(radios.count()):
                    radio = radios.nth(j)
                    radio_id = radio.get_attribute("id")
                    value = radio.get_attribute("value")

                    if radio_id:
                        label = fieldset.locator(f"label[for='{radio_id}']").first
                        text = (label.inner_text() or "").strip()
                        if text:
                            choices.append(text)
                            continue

                    if value:
                        choices.append(value)

                field_id = f"radio_{i}"
                questions.append(Question(id=field_id, type="radio", question=legend, choices=choices))
                field_map[field_id] = fieldset

            except Exception:
                continue

    # ------------------------------------------------------------------ #
    # Answer filling
    # ------------------------------------------------------------------ #
    @staticmethod
    def _apply_answer(field: Locator, field_type: str, value: str) -> None:
        if field_type == "text":
            field.fill(value)

        elif field_type == "select":
            field.select_option(label=value)

        elif field_type == "radio":
            try:
                field.get_by_label(value, exact=True).check()
                return
            except Exception:
                pass

            label = field.get_by_text(value, exact=True).first
            if label.count():
                label.click()
                return

            radio = field.locator(f"input[type='radio'][value='{value}']").first
            radio.check()

    # ------------------------------------------------------------------ #
    # "Answer yes" heuristic for technical yes/no fieldsets
    # ------------------------------------------------------------------ #
    @staticmethod
    def answer_yes_to_technical_questions(scope: Locator, legend_selector: str = "legend") -> None:
        fieldsets = scope.locator("fieldset")
        for i in range(fieldsets.count()):
            fieldset = fieldsets.nth(i)
            try:
                question = fieldset.locator(legend_selector).first.inner_text().lower()
                if not any(keyword in question for keyword in TECHNICAL_KEYWORDS):
                    continue

                labels = fieldset.locator("label")
                for j in range(labels.count()):
                    label = labels.nth(j)
                    if label.inner_text().strip().lower() == "yes":
                        label.click()
                        break

            except Exception:
                continue
