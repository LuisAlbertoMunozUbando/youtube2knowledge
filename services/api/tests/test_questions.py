import pytest

from app.models import CreateJobRequest, GeneratedQuestion, QuestionType
from app.providers.questions import (
    QuestionGenerationError,
    _extract_json,
    _validate_grounding,
    build_prompt,
)


def request() -> CreateJobRequest:
    return CreateJobRequest(
        youtube_url="https://youtu.be/dQw4w9WgXcQ",
        question_types=[QuestionType.WHAT, QuestionType.WHY],
        custom_questions=["What is the conclusion?"],
        keywords=["robotics"],
        questions_per_type=2,
        output_language="en",
    )


def test_prompt_contains_constraints() -> None:
    prompt = build_prompt("Transcript body", request())
    assert "What, Why" in prompt
    assert "robotics" in prompt
    assert "up to 2" in prompt
    assert "fewer questions" in prompt
    assert "Transcript body" in prompt


def test_extracts_fenced_json() -> None:
    parsed = _extract_json('```json\n{"questions": []}\n```')
    assert parsed == {"questions": []}


def test_rejects_invalid_json() -> None:
    with pytest.raises(QuestionGenerationError):
        _extract_json("not json")


def test_accepts_verbatim_grounding_ignoring_case_and_whitespace() -> None:
    questions = [
        GeneratedQuestion(
            type="What",
            question="What does the robot learn?",
            answer="It learns to walk.",
            evidence="THE ROBOT   learns to walk",
        )
    ]
    _validate_grounding(questions, "The robot learns to walk safely.", request())


def test_rejects_evidence_missing_from_transcript() -> None:
    questions = [
        GeneratedQuestion(
            type="Why",
            question="Why is local inference private?",
            answer="Data remains local.",
            evidence="Data remains local.",
        )
    ]
    with pytest.raises(QuestionGenerationError, match="not present"):
        _validate_grounding(questions, "DGX Spark runs AI models.", request())


def test_rejects_selected_question_without_evidence() -> None:
    questions = [
        GeneratedQuestion(
            type="Why",
            question="Why?",
            answer="Not stated in the transcript.",
            evidence="",
        )
    ]
    with pytest.raises(QuestionGenerationError, match="ungrounded"):
        _validate_grounding(questions, "A short transcript.", request())


def test_allows_unanswered_custom_question() -> None:
    questions = [
        GeneratedQuestion(
            type="Custom",
            question="What is the conclusion?",
            answer="The transcript does not say.",
            evidence="",
        )
    ]
    _validate_grounding(questions, "A short transcript.", request())
