import pytest

from app.models import CreateJobRequest, GeneratedQuestion, QuestionType
from app.providers.questions import (
    QuestionGenerationError,
    _align_evidence,
    _align_question_evidence,
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


def test_aligns_noisy_model_quote_to_exact_transcript_excerpt() -> None:
    transcript = (
        "NVIDIA DLSS Five introduces 3D guided neural rendering, an AI model "
        "designed to bring real-time graphics closer."
    )
    noisy_evidence = (
        "Nvidia theelsis five introduces tres d guided neurorendering, un ai "
        "model designed to bring real time graphics closer."
    )

    aligned = _align_evidence(noisy_evidence, transcript)

    assert aligned == transcript.removesuffix(".")


def test_drops_question_when_evidence_cannot_be_aligned() -> None:
    questions = [
        GeneratedQuestion(
            type="Why",
            question="Why is the system private?",
            answer="Because all data remains local.",
            evidence="All private data remains on the device.",
        ),
        GeneratedQuestion(
            type="What",
            question="What does the system run?",
            answer="AI models.",
            evidence="The system runs AI models.",
        ),
    ]

    aligned = _align_question_evidence(
        questions,
        "The system runs AI models.",
    )

    assert [item.type for item in aligned] == ["What"]
    assert aligned[0].evidence == "The system runs AI models"
