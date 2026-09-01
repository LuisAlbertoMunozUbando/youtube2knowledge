import pytest

from app.models import CreateJobRequest, QuestionType
from app.providers.questions import QuestionGenerationError, _extract_json, build_prompt


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
    assert "exactly 2" in prompt
    assert "Transcript body" in prompt


def test_extracts_fenced_json() -> None:
    parsed = _extract_json('```json\n{"questions": []}\n```')
    assert parsed == {"questions": []}


def test_rejects_invalid_json() -> None:
    with pytest.raises(QuestionGenerationError):
        _extract_json("not json")
