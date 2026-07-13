from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Locator

from ai.openai_client import AIClient
from core.logging import AppLogger


@dataclass
class XingQuestion:
    id: str
    type: str  # "text" | "date" | "select" | "radio"
    question: str
    choices: list[str] | None = None


class XingFormFiller:
    """Discovers unanswered fields in Xing's Easy Apply wizard.

    Xing's wizard (Radix/XDS component library) labels fields differently
    from JobStreet/LinkedIn: question text sits in a heading tied via
    aria-labelledby rather than <label for=...>, and radio choices are
    grouped in <ul data-xds="RadioButtonGroup"> instead of <fieldset><legend>.
    Kept isolated from the shared FormFiller since neither field discovery
    nor answer application overlaps cleanly.
    """

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        self.console = AppLogger.console()
        self.app = "[Applier]"

    def fill(self, scope: Locator, confidence_threshold: int = 90) -> bool:
        questions: list[XingQuestion] = []
        field_map: dict[str, Locator] = {}

        self._discover_text_fields(scope, questions, field_map)
        self._discover_date_fields(scope, questions, field_map)
        self._discover_select_fields(scope, questions, field_map)
        self._discover_radio_fields(scope, questions, field_map)

        if not questions:
            return True

        self.console.print(f"[cyan]{self.app} Answering {len(questions)} form question(s) via AI...[/cyan]")

        answers = self.ai_client.answer_application_questions(
            [{"id": q.id, "type": q.type, "question": q.question, "choices": q.choices} for q in questions]
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
    @staticmethod
    def _label_for(scope: Locator, field: Locator) -> str:
        labelledby = field.get_attribute("aria-labelledby")
        if labelledby:
            heading = scope.locator(f"#{labelledby}")
            if heading.count():
                text = (heading.first.inner_text() or "").strip()
                if text:
                    return text

        field_id = field.get_attribute("id")
        if field_id:
            label = scope.locator(f"label[for='{field_id}']").first
            if label.count():
                text = (label.inner_text() or "").strip()
                if text:
                    return text

        return ""

    def _discover_text_fields(self, scope: Locator, questions: list[XingQuestion], field_map: dict[str, Locator]) -> None:
        fields = scope.locator("input[data-xds='FormField']:not([type='date'])")
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

                question_text = self._label_for(scope, field)
                if not question_text:
                    continue

                questions.append(XingQuestion(id=field_id, type="text", question=question_text))
                field_map[field_id] = field

            except Exception:
                continue

    def _discover_date_fields(self, scope: Locator, questions: list[XingQuestion], field_map: dict[str, Locator]) -> None:
        fields = scope.locator("input[type='date']")
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

                question_text = self._label_for(scope, field)
                if not question_text:
                    continue

                questions.append(XingQuestion(id=field_id, type="date", question=f"{question_text} (answer as YYYY-MM-DD)"))
                field_map[field_id] = field

            except Exception:
                continue

    def _discover_select_fields(self, scope: Locator, questions: list[XingQuestion], field_map: dict[str, Locator]) -> None:
        selects = scope.locator("select[data-xds='Dropdown']")
        for i in range(selects.count()):
            select = selects.nth(i)
            try:
                if not select.is_visible():
                    continue

                select_id = select.get_attribute("id")
                if not select_id:
                    continue

                current_value = (select.input_value() or "").strip()
                if current_value:
                    continue

                question_text = self._label_for(scope, select)
                if not question_text:
                    continue

                options = []
                option_nodes = select.locator("option")
                for j in range(option_nodes.count()):
                    text = option_nodes.nth(j).inner_text().strip()
                    value = option_nodes.nth(j).get_attribute("value") or ""
                    if not text or not value:
                        continue
                    options.append(text)

                if not options:
                    continue

                questions.append(XingQuestion(id=select_id, type="select", question=question_text, choices=options))
                field_map[select_id] = select

            except Exception:
                continue

    def _discover_radio_fields(self, scope: Locator, questions: list[XingQuestion], field_map: dict[str, Locator]) -> None:
        groups = scope.locator("ul[data-xds='RadioButtonGroup']")
        for i in range(groups.count()):
            group = groups.nth(i)
            try:
                labelledby = group.get_attribute("aria-labelledby")
                if not labelledby:
                    continue

                heading = scope.locator(f"#{labelledby}")
                if not heading.count():
                    continue
                question_text = (heading.first.inner_text() or "").strip()
                if not question_text:
                    continue

                radios = group.locator("input[type='radio']")

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
                    labelledby_option = radio.get_attribute("aria-labelledby")
                    if labelledby_option:
                        option_label = group.locator(f"#{labelledby_option}")
                        text = (option_label.inner_text() or "").strip() if option_label.count() else ""
                        if text:
                            choices.append(text)
                            continue

                    value = radio.get_attribute("value")
                    if value:
                        choices.append(value)

                if not choices:
                    continue

                field_id = f"radio_{i}"
                questions.append(XingQuestion(id=field_id, type="radio", question=question_text, choices=choices))
                field_map[field_id] = group

            except Exception:
                continue

    # ------------------------------------------------------------------ #
    # Answer filling
    # ------------------------------------------------------------------ #
    @staticmethod
    def _apply_answer(field: Locator, field_type: str, value: str) -> None:
        if field_type in ("text", "date"):
            field.fill(value)

        elif field_type == "select":
            field.select_option(label=value)

        elif field_type == "radio":
            label = field.get_by_text(value, exact=True).first
            if label.count():
                label.click()
                return

            radio = field.locator(f"input[type='radio'][value='{value}']").first
            radio.check()
