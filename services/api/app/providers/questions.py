import json
import re

import httpx

from ..config import Settings
from ..models import CreateJobRequest, GeneratedQuestion


class QuestionGenerationError(RuntimeError):
    pass


def build_prompt(transcript: str, request: CreateJobRequest) -> str:
    types = ", ".join(item.value for item in request.question_types)
    custom = "\n".join(f"- {item}" for item in request.custom_questions) or "- None"
    keywords = ", ".join(request.keywords) or "None"
    language = {
        "auto": "the transcript's primary language",
        "en": "English",
        "es": "Spanish",
    }[request.output_language]

    return f"""You are an educational question generator. Use only the supplied transcript.

Generate exactly {request.questions_per_type} questions for each selected question type:
{types}

Also answer every custom question when the transcript contains enough evidence:
{custom}

Prioritize these keywords when relevant: {keywords}
Write questions and answers in {language}.

Rules:
- Every answer must be supported by the transcript; never invent facts.
- Evidence must be a short verbatim excerpt from the transcript.
- If a custom question cannot be answered, say so explicitly and use an empty evidence string.
- The `type` field must be one selected type or `Custom`.
- Return JSON only, matching this shape:
{{"questions":[{{"type":"What","question":"...","answer":"...","evidence":"..."}}]}}

TRANSCRIPT:
{transcript}
"""


def _extract_json(raw: str) -> dict[str, object]:
    cleaned = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise QuestionGenerationError("The model did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise QuestionGenerationError("The model response must be a JSON object")
    return parsed


def generate_questions(
    transcript: str,
    request: CreateJobRequest,
    settings: Settings,
) -> list[GeneratedQuestion]:
    endpoint = f"{settings.llm_api_base_url.rstrip('/')}/chat/completions"
    headers: dict[str, str] = {}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    payload = {
        "model": settings.llm_model,
        "temperature": 0.2,
        "max_tokens": settings.llm_max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "Return grounded educational questions as strict JSON.",
            },
            {"role": "user", "content": build_prompt(transcript, request)},
        ],
    }
    response = httpx.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=settings.llm_timeout_seconds,
    )
    if response.status_code in {400, 422}:
        # Some OpenAI-compatible endpoints (including selected NIM deployments)
        # do not expose response_format even though they return JSON reliably.
        payload.pop("response_format")
        response = httpx.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=settings.llm_timeout_seconds,
        )
    if response.is_error:
        raise QuestionGenerationError(f"LLM API returned {response.status_code}")
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise QuestionGenerationError("Unexpected LLM API response") from exc

    parsed = _extract_json(content)
    raw_questions = parsed.get("questions")
    if not isinstance(raw_questions, list):
        raise QuestionGenerationError("The model response has no questions array")
    allowed = {item.value for item in request.question_types} | {"Custom"}
    questions = [GeneratedQuestion.model_validate(item) for item in raw_questions]
    invalid = {item.type for item in questions} - allowed
    if invalid:
        raise QuestionGenerationError(f"Model returned unrequested types: {sorted(invalid)}")
    return questions
