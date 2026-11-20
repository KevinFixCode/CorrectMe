# CorrectMe

[![Tests](https://github.com/KevinFixCode/CorrectMe/actions/workflows/tests.yml/badge.svg)](https://github.com/KevinFixCode/CorrectMe/actions/workflows/tests.yml)

An open-source AI speaking coach that helps you become a fluent English speaker by practising real conversations.

1. **Listen**: the app hears what your conversation partner says.
2. **Reply**: AI writes polished, high-level replies (IELTS band 9 style) as **text only**. No audio is generated for you.
3. **Speak**: you read the reply aloud, yourself.
4. **Score**: AI checks your pronunciation word by word.

Reading advanced replies out loud trains your tongue, and the target words from every reply go into a spaced-repetition deck, so vocabulary sticks without rote memorising.

> *Bahasa Indonesia:* CorrectMe mendengar lawan bicara, menuliskan balasan level tinggi (teks saja), kamu membacanya dengan suara sendiri, lalu AI menilai pronunciation kamu. Kata-kata barunya otomatis masuk ke kartu hafalan.

## Use it on your phone (web app)

CorrectMe also runs as a web page, so there is nothing to install: open it in your phone's browser, add it to the home screen, and practise.

- **Free for everyone, no server.** The page runs entirely in the browser. Each person brings their own API key (for example a free key from [console.groq.com](https://console.groq.com)), so there is no shared quota to run out. Free tiers have their own rate limits.
- **Your data stays on your device.** The key and your vocabulary deck are stored in the browser only. Your speech and text go to the speech and AI services you choose.
- **Two speech engines** (Settings): the browser's built-in recognition (free and fast, but it tends to forgive mistakes) or Whisper through your API key (stricter, and it works on iPhone).
- Phoneme-level scoring is desktop-only for now, because it needs a heavy model.

**Publish your own copy for free (GitHub Pages):** in your fork go to *Settings, Pages*, choose *Deploy from a branch*, branch `main`, folder `/docs`, and save. The page appears at `https://<your-username>.github.io/CorrectMe/`.

To try it locally: `python -m http.server 8000 --directory docs`, then open `http://localhost:8000`.

## Quick start

Requirements: Python 3.10+ (3.12 recommended; very new Python versions may lack wheels for some dependencies), a microphone for the full loop, and an LLM (free local [Ollama](https://ollama.com) or an API key).

```bash
git clone https://github.com/KevinFixCode/CorrectMe.git
cd CorrectMe

python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\activate | Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt  # Linux may also need: sudo apt install libportaudio2

cp .env.example .env             # then edit the LLM settings
```

For the free local setup: install Ollama, run `ollama pull llama3.1`, and keep `LLM_PROVIDER=ollama` in `.env`.

### Choosing an LLM

CorrectMe works with any of these. Set them in `.env`.

| Option | `.env` settings |
| --- | --- |
| **Ollama** (local, free, large download) | `LLM_PROVIDER=ollama`, `LLM_MODEL=llama3.1` |
| **Groq** (hosted, free tier available, no big download) | `LLM_PROVIDER=openai`, `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=<a chat model>`, `LLM_API_KEY=<your key>` |
| **OpenAI or other OpenAI-compatible APIs** | `LLM_PROVIDER=openai`, `LLM_BASE_URL=<endpoint>`, `LLM_MODEL=<model>`, `LLM_API_KEY=<key>` |
| **Anthropic** | `LLM_PROVIDER=anthropic`, `LLM_MODEL=<model>`, `LLM_API_KEY=<key>` |

Hosted model names change over time. If you get `model_not_found` (HTTP 404), list the models your key can use and pick a chat model (skip `whisper`, `guard` and `tts` models):

```bash
python -c "import json,urllib.request as u;from core.config import load_settings as l;s=l();r=u.Request(s.llm_base_url+'/models',headers={'Authorization':'Bearer '+s.llm_api_key,'User-Agent':'CorrectMe/0.1'});print('\\n'.join(sorted(m['id'] for m in json.load(u.urlopen(r))['data'])))"
```

Tested with Groq and `openai/gpt-oss-120b`. Never share or commit your API key; `.env` is already in `.gitignore`.

**Troubleshooting**

- `HTTP 403 ... error code: 1010`: the provider's firewall rejected the request. Update to the latest CorrectMe (it sends its own `User-Agent`).
- `HTTP 404 model_not_found`: the model name is wrong or not available to your account. List models as shown above.
- `HTTP 401`: the API key is wrong or was revoked.
- `Cannot reach the LLM server`: with Ollama, start the Ollama app first.

The first run downloads the Whisper model set by `WHISPER_MODEL` (default `small`, roughly 460 MB). Use `base.en` for a smaller, faster start.

## Usage

```bash
# Full loop with your microphone
python main.py practice

# Try it without a microphone for your partner
python main.py practice --partner-text "So, what brought you to this field?"

# Choose the difficulty: B1, B2, C1 or C2
python main.py practice --level C1

# Score a recording against a sentence
python main.py score --text "I would be delighted to join you." --audio me.wav

# Review the vocabulary you collected (spaced repetition)
python main.py review
```

Each practice turn shows a **natural** reply and an **advanced** reply, 2-4 target words with meanings, then scores you word by word and tells you which words to practise.

No microphone yet? `score` works on any audio file. `practice` still needs a microphone for the read-aloud step.

## How the scoring works (and its limits)

Your recording is transcribed by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and aligned against the sentence you were meant to read. A word scores high when it is recognised correctly **and** with high confidence.

This measures *intelligibility*, not phoneme-level accuracy, and Whisper is forgiving of accents. Treat the score as "would a listener understand this word", not as an exam result. Every word that is wrong or not heard also lowers the overall score by 10 points, so a few missed words cannot hide behind many correct ones. For individual sounds, add `--phonemes` to `score` (see below).

## Phoneme-level scoring (optional)

`score --phonemes` also checks individual sounds, for example `th` said as `s`, or `l` and `r` swapped.

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-phonemes.txt
python main.py score --text "I think so." --audio me.wav --phonemes
```

The first run downloads a wav2vec2 phoneme model (about 1.2 GB). Scoring weights are a first guess and have not yet been tuned on real learner recordings.

## Project layout

```
main.py                 command-line interface
core/
  config.py             settings from .env / environment
  stt.py                faster-whisper speech-to-text
  recorder.py           microphone recording
  reply.py              LLM prompts + reply parsing (OpenAI-compatible and Anthropic)
  pronunciation.py      word alignment and scoring
  phonemes.py           phoneme scoring logic (ARPAbet, CMU dictionary)
  recognizer.py         wav2vec2 phoneme recogniser (optional, needs torch + transformers)
  vocab.py              SQLite vocabulary deck with SM-2 spaced repetition
docs/                   web app (static PWA, published with GitHub Pages)
  lib.js                scoring, spaced repetition and prompts (port of the Python logic)
  app.js                user interface, speech capture and API calls
tests/                  Python unit tests
tests_js/               web app tests (checked against Python results)
```

Run the tests (no network or model downloads needed):

```bash
python -m unittest discover -s tests -t .
node --test "tests_js/*.test.js"      # web app tests (Node 20+)
```

## Roadmap

- [x] Web interface for phones (`docs/`), bring your own API key
- [x] Phoneme-level scoring (wav2vec2), available as `score --phonemes`
- [ ] Tune the phoneme scoring weights on real learner recordings
- [ ] Stress and intonation feedback
- [ ] FSRS scheduling option
- [ ] Mobile app

## Contributing

Issues and pull requests are welcome. Good first tasks: improve the prompts in `core/reply.py`, add tests, or help with the roadmap above.

## License

MIT
