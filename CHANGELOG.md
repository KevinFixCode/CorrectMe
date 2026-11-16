# Changelog

## 0.1.0 - 2026-11-16

First public release.

- Practice loop: listen to the partner, get a natural and an advanced reply (text only), read it aloud, get scored.
- Word-level pronunciation scoring with faster-whisper; wrong or missing words lower the overall score.
- Optional phoneme-level scoring with wav2vec2 (`score --phonemes`).
- Spaced-repetition vocabulary deck (SM-2) stored in SQLite, reviewed with `review`.
- Works with Ollama, OpenAI-compatible APIs and the Anthropic API.
- Microphone selection (`--device`, `devices`).
