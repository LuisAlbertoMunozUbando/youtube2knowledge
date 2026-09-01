import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

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

Generate up to {request.questions_per_type} well-supported questions for each
selected question type:
{types}

Also answer every custom question when the transcript contains enough evidence:
{custom}

Prioritize these keywords when relevant: {keywords}
Write questions and answers in {language}.

Rules:
- Every answer must be supported by the transcript; never invent facts.
- Evidence must be a short verbatim excerpt from the transcript.
- Omit a selected question type when the transcript has no evidence for it.
- Returning fewer questions is always better than returning an unsupported answer.
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


def _normalize_quote(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def _alignment_tokens(value: str) -> list[str]:
    return re.findall(r"\w+", _normalize_quote(value), flags=re.UNICODE)


def _align_evidence(evidence: str, transcript: str) -> str | None:
    evidence_tokens = _alignment_tokens(evidence)
    transcript_matches = list(re.finditer(r"\w+", transcript, flags=re.UNICODE))
    transcript_tokens = [
        _normalize_quote(match.group())
        for match in transcript_matches
    ]
    if not evidence_tokens or not transcript_tokens:
        return None

    evidence_text = " ".join(evidence_tokens)
    evidence_length = len(evidence_tokens)
    minimum_length = max(1, evidence_length - 4)
    maximum_length = min(len(transcript_tokens), evidence_length + 4)
    best: tuple[float, float, int, int] | None = None

    transcript_positions: dict[str, list[int]] = {}
    for index, token in enumerate(transcript_tokens):
        transcript_positions.setdefault(token, []).append(index)
    shared_tokens = sorted(
        (
            (len(transcript_positions[token]), evidence_index, token)
            for evidence_index, token in enumerate(evidence_tokens)
            if token in transcript_positions
        ),
        key=lambda item: item[0],
    )
    if not shared_tokens:
        return None
    candidate_starts: set[int] = set()
    for _, evidence_index, token in shared_tokens[:6]:
        for transcript_index in transcript_positions[token]:
            estimated_start = transcript_index - evidence_index
            candidate_starts.update(range(estimated_start - 4, estimated_start + 5))

    for length in range(minimum_length, maximum_length + 1):
        for start in candidate_starts:
            if start < 0 or start + length > len(transcript_tokens):
                continue
            end = start + length
            candidate_tokens = transcript_tokens[start:end]
            candidate_text = " ".join(candidate_tokens)
            character_score = SequenceMatcher(None, evidence_text, candidate_text).ratio()
            if best is not None and character_score < best[0]:
                continue
            token_score = SequenceMatcher(None, evidence_tokens, candidate_tokens).ratio()
            candidate = (character_score, token_score, start, end)
            if best is None or candidate[:2] > best[:2]:
                best = candidate

    if best is None:
        return None
    character_score, token_score, start, end = best
    if evidence_length < 5:
        accepted = character_score >= 0.92 and token_score >= 0.80
    else:
        accepted = character_score >= 0.82 and token_score >= 0.60
    if not accepted:
        return None

    return transcript[
        transcript_matches[start].start():transcript_matches[end - 1].end()
    ]


def _align_question_evidence(
    questions: list[GeneratedQuestion],
    transcript: str,
) -> list[GeneratedQuestion]:
    aligned_questions: list[GeneratedQuestion] = []
    for item in questions:
        if not item.evidence.strip():
            if item.type == "Custom":
                aligned_questions.append(item)
            continue
        aligned_evidence = _align_evidence(item.evidence, transcript)
        if aligned_evidence is None:
            continue
        item.evidence = aligned_evidence
        aligned_questions.append(item)
    return aligned_questions


def _validate_grounding(
    questions: list[GeneratedQuestion],
    transcript: str,
    request: CreateJobRequest,
) -> None:
    normalized_transcript = _normalize_quote(transcript)
    counts = Counter(item.type for item in questions)
    excessive = {
        question_type: count
        for question_type, count in counts.items()
        if question_type != "Custom" and count > request.questions_per_type
    }
    if excessive:
        raise QuestionGenerationError(f"Model returned too many questions: {excessive}")

    for item in questions:
        evidence = _normalize_quote(item.evidence)
        if not evidence:
            if item.type == "Custom":
                continue
            raise QuestionGenerationError(
                f"Model returned an ungrounded {item.type} question"
            )
        if evidence not in normalized_transcript:
            raise QuestionGenerationError(
                f"Model evidence for {item.type} is not present in the transcript"
            )


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
    questions = _align_question_evidence(questions, transcript)
    if not questions:
        raise QuestionGenerationError("The model returned no grounded questions")
    _validate_grounding(questions, transcript, request)
    return questions
