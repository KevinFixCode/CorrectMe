# Changelog

## Unreleased

- Koreksi mode in the web app: correct grammar and word choice in free speech or text from any speaker, with a corrected and a polished version, and a shortcut to read the corrected sentence aloud for scoring.
- Web app for phones and browsers (`docs/`): installable PWA, no server needed. Bring your own API key (for example a free Groq key).
- Two speech engines: the browser's built-in recognition, or Whisper through your API key (also works on iPhone).
- Word-level scoring ported to JavaScript and checked against the Python results (`tests_js/`).
- Send a custom `User-Agent` so Groq/Cloudflare no longer rejects requests (HTTP 403, error 1010).
- README: LLM options, Groq setup and troubleshooting.

## 0.1.0 - 2026-11-16

First public release.

- Practice loop: listen to the partner, get a natural and an advanced reply (text only), read it aloud, get scored.
- Word-level pronunciation scoring with faster-whisper; wrong or missing words lower the overall score.
- Optional phoneme-level scoring with wav2vec2 (`score --phonemes`).
- Spaced-repetition vocabulary deck (SM-2) stored in SQLite, reviewed with `review`.
- Works with Ollama, OpenAI-compatible APIs and the Anthropic API.
- Microphone selection (`--device`, `devices`).
