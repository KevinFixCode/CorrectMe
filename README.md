# CorrectMe

[![Tests](https://github.com/KevinFixCode/CorrectMe/actions/workflows/tests.yml/badge.svg)](https://github.com/KevinFixCode/CorrectMe/actions/workflows/tests.yml)

An open-source AI speaking coach that helps you become a fluent English speaker by practising real conversations.

1. **Listen**: the app hears what your conversation partner says.
2. **Reply**: AI writes polished, high-level replies (IELTS band 9 style) as **text only**. No audio is generated for you.
3. **Speak**: you read the reply aloud, yourself.
4. **Score**: AI checks your pronunciation word by word.

Reading advanced replies out loud trains your tongue, and the target words from every reply go into a spaced-repetition deck, so vocabulary sticks without rote memorising.

> *Bahasa Indonesia:* CorrectMe mendengar lawan bicara, menuliskan balasan level tinggi (teks saja), kamu membacanya dengan suara sendiri, lalu AI menilai pronunciation kamu. Kata-kata barunya otomatis masuk ke kartu hafalan.

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
tests/                  unit tests
```

Run the tests (no network or model downloads needed):

```bash
python -m unittest discover -s tests -t .
```

## Roadmap

- [ ] Web interface (live partner audio, side-by-side replies, highlighted target words)
- [x] Phoneme-level scoring (wav2vec2), available as `score --phonemes`
- [ ] Tune the phoneme scoring weights on real learner recordings
- [ ] Stress and intonation feedback
- [ ] FSRS scheduling option
- [ ] Mobile app

## Contributing

Issues and pull requests are welcome. Good first tasks: improve the prompts in `core/reply.py`, add tests, or help with the roadmap above.

## License

MIT
