"""Reply generation: turn what the partner said into high-level replies the learner can read aloud.

Talks to any OpenAI-compatible chat endpoint (OpenAI, Ollama, LM Studio, OpenRouter, ...)
or to the Anthropic Messages API. Only the standard library is used for HTTP.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .config import Settings

LEVELS = {
    "B1": "CEFR B1: clear everyday English, simple connectors, common phrasal verbs.",
    "B2": "CEFR B2: fluent and fairly precise English, a range of connectors, some idioms.",
    "C1": (
        "CEFR C1 / IELTS band 7-8: flexible, precise English with less common vocabulary, "
        "collocations and complex sentence structures."
    ),
    "C2": (
        "CEFR C2 / IELTS band 9: effortless, idiomatic, highly precise English with "
        "sophisticated vocabulary and a wide range of complex grammar used naturally."
    ),
}


# Some providers (e.g. Groq behind Cloudflare) reject urllib's default User-Agent with HTTP 403 / error 1010.
USER_AGENT = "CorrectMe/0.1 (+https://github.com/KevinFixCode/CorrectMe)"


class LLMError(RuntimeError):
    """Raised when the language model cannot be reached or returns an error."""


@dataclass
class TargetWord:
    word: str
    meaning: str = ""
    example: str = ""


@dataclass
class Reply:
    natural: str
    advanced: str
    target_words: list = field(default_factory=list)  # list[TargetWord]

    def pick(self, version: str) -> str:
        return self.advanced if version == "advanced" else self.natural


# --------------------------------------------------------------------------- prompts

def build_system_prompt(level: str, native_language: str) -> str:
    level_desc = LEVELS.get(level.upper())
    if level_desc is None:
        raise ValueError(f"Unknown level '{level}'. Choose one of: {', '.join(LEVELS)}")
    return (
        "You are CorrectMe, an English speaking coach. The learner is a non-native speaker "
        "who will READ your reply aloud to a real conversation partner, so it must sound "
        "natural when spoken.\n\n"
        "Task: given what the conversation partner just said, write replies the learner "
        "can say back.\n"
        f"Target register: {level_desc}\n\n"
        "Rules:\n"
        "- Respond to what the partner actually said, directly and in context. Never ignore "
        "a question.\n"
        "- Replies are spoken aloud: 2-3 sentences, no bullet points, no emojis, no stage "
        "directions.\n"
        '- "natural": polished and idiomatic, the way an articulate native speaker would '
        "really say it.\n"
        '- "advanced": the same intent, but showcasing richer vocabulary, precise '
        "collocations and one sophisticated grammar structure (for example inversion, a "
        "mixed conditional, a cleft sentence or a participle clause) without sounding "
        "stilted.\n"
        "- Choose 2-4 target_words that appear verbatim in your replies and are worth "
        f"learning. Give a short meaning in {native_language} and a short English example "
        "sentence.\n"
        "- Respond with ONLY a JSON object, no markdown fences, in exactly this shape:\n"
        '{"natural": "...", "advanced": "...", '
        '"target_words": [{"word": "...", "meaning": "...", "example": "..."}]}'
    )


def build_user_prompt(partner_text: str, history=None) -> str:
    lines = []
    if history:
        lines.append("Conversation so far:")
        for partner, learner in history[-4:]:
            lines.append(f"Partner: {partner}")
            lines.append(f"Learner: {learner}")
        lines.append("")
    lines.append(f'Partner (just now): "{partner_text.strip()}"')
    return "\n".join(lines)


# --------------------------------------------------------------------------- parsing

def _extract_json(raw: str):
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_reply(raw: str) -> Reply:
    """Parse the model output. Falls back gracefully if it is not valid JSON."""
    data = _extract_json(raw)
    if data is None:
        text = raw.strip()
        if not text:
            raise LLMError("The language model returned an empty reply.")
        return Reply(natural=text, advanced=text)

    natural = str(data.get("natural") or data.get("reply") or "").strip()
    advanced = str(data.get("advanced") or "").strip()
    if not natural and not advanced:
        raise LLMError("The language model reply had no usable text.")
    natural = natural or advanced
    advanced = advanced or natural

    targets = []
    for item in data.get("target_words") or []:
        if isinstance(item, dict) and str(item.get("word", "")).strip():
            targets.append(
                TargetWord(
                    word=str(item["word"]).strip(),
                    meaning=str(item.get("meaning", "")).strip(),
                    example=str(item.get("example", "")).strip(),
                )
            )
    return Reply(natural=natural, advanced=advanced, target_words=targets)


# --------------------------------------------------------------------------- HTTP

def _post_json(url: str, payload: dict, headers: dict, timeout: int = 90) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise LLMError(f"LLM request failed (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Cannot reach the LLM server at {url}: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc


def complete(settings: Settings, system: str, user: str) -> str:
    """Send one system+user prompt to the configured provider and return the text."""
    if settings.llm_provider == "anthropic":
        if not settings.llm_api_key:
            raise LLMError("LLM_API_KEY is not set (required for the anthropic provider).")
        data = _post_json(
            f"{settings.llm_base_url}/v1/messages",
            {
                "model": settings.llm_model,
                "max_tokens": 800,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            {"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01"},
        )
        try:
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected response from Anthropic API: {data}") from exc

    # openai-compatible (openai, ollama, ...)
    headers = {}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    elif settings.llm_provider == "openai":
        raise LLMError("LLM_API_KEY is not set (required for the openai provider).")
    data = _post_json(
        f"{settings.llm_base_url}/chat/completions",
        {
            "model": settings.llm_model,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        headers,
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected response from LLM server: {data}") from exc


def generate_reply(settings: Settings, partner_text: str, level: str | None = None, history=None) -> Reply:
    """Generate a 'natural' and an 'advanced' reply plus target vocabulary."""
    if not partner_text.strip():
        raise ValueError("partner_text is empty")
    system = build_system_prompt(level or settings.level, settings.native_language)
    user = build_user_prompt(partner_text, history)
    return parse_reply(complete(settings, system, user))
