#!/usr/bin/env python3
"""CorrectMe command-line interface.

    python main.py practice            # full loop with microphone
    python main.py practice --partner-text "So, what do you do for a living?"
    python main.py score --text "I would love to" --audio me.wav
    python main.py review              # flashcards for the words you collected
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from core import __version__
from core.config import Settings, load_settings
from core.pronunciation import WEAK_THRESHOLD, PronunciationResult, score_pronunciation
from core.reply import LEVELS, LLMError, generate_reply
from core.stt import Transcriber
from core.vocab import VocabDeck

# --------------------------------------------------------------------------- output helpers

_COLORS = {"green": "32", "yellow": "33", "red": "31", "cyan": "36", "dim": "2", "bold": "1"}


def paint(text: str, color: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{_COLORS[color]}m{text}\033[0m"


def print_result(result: PronunciationResult) -> None:
    color = "green" if result.overall >= 85 else "yellow" if result.overall >= WEAK_THRESHOLD else "red"
    print(f"\n  Pronunciation score: {paint(str(result.overall) + '/100', color)}")
    for w in result.words:
        if w.status == "correct" and w.score >= WEAK_THRESHOLD:
            print(f"    {paint('✓', 'green')} {w.reference} ({w.score})")
        elif w.status == "missing":
            print(f"    {paint('✗', 'red')} {w.reference}  (not heard)")
        else:
            heard = f"heard '{w.heard}'" if w.heard and w.heard != w.reference else "unclear"
            print(f"    {paint('~', 'yellow')} {w.reference}  ({w.score}, {heard})")
    if result.extra:
        print(paint(f"    extra words heard: {' '.join(result.extra)}", "dim"))
    weak = result.weak_words()
    if weak:
        print(f"  Practise: {paint(', '.join(w.reference for w in weak), 'bold')}")
    else:
        print(paint("  Clear and confident. Nicely done!", "green"))


def make_transcriber(settings: Settings) -> Transcriber:
    return Transcriber(settings.whisper_model, settings.whisper_device, settings.whisper_compute_type)


# --------------------------------------------------------------------------- commands

def cmd_practice(args: argparse.Namespace) -> int:
    from core.recorder import record_until_enter

    settings = load_settings()
    level = (args.level or settings.level).upper()
    if level not in LEVELS:
        print(f"Unknown level '{level}'. Choose one of: {', '.join(LEVELS)}")
        return 2

    transcriber = make_transcriber(settings)
    deck = VocabDeck(settings.db_path)
    one_shot = bool(args.partner_text or args.partner_audio)
    history: list = []

    print(paint(f"CorrectMe {__version__} · level {level} · Ctrl+C to quit", "dim"))
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        turn = 0
        while True:
            turn += 1
            print(paint(f"\n── Turn {turn} ──", "cyan"))

            # 1. Listen to the conversation partner
            if args.partner_text:
                partner_text = args.partner_text
            elif args.partner_audio:
                partner_text = transcriber.transcribe(args.partner_audio, args.language).text
            else:
                audio = record_until_enter(workdir / "partner.wav", "Press Enter, then let your partner speak")
                partner_text = transcriber.transcribe(audio, args.language).text
            if not partner_text:
                print("  I didn't catch anything. Try again.")
                if one_shot:
                    return 1
                continue
            print(f"  Partner: {paint(partner_text, 'bold')}")

            # 2. Write replies (text only, no audio)
            try:
                reply = generate_reply(settings, partner_text, level, history)
            except LLMError as exc:
                print(paint(f"  {exc}", "red"))
                if one_shot:
                    return 1
                continue

            print(f"\n  [1] Natural : {reply.natural}")
            print(f"  [2] Advanced: {paint(reply.advanced, 'cyan')}")
            if reply.target_words:
                print("\n  Target words:")
                for tw in reply.target_words:
                    print(f"    • {paint(tw.word, 'bold')}: {tw.meaning}")
                    if tw.example:
                        print(paint(f"      “{tw.example}”", "dim"))
                    deck.add(tw.word, tw.meaning, tw.example)

            # 3. Learner picks a version and reads it aloud
            choice = input("\n  Read which? [1] natural  [2] advanced (default)  [n] next turn  [q] quit > ").strip().lower()
            if choice == "q":
                break
            if choice == "n":
                continue
            version = "natural" if choice == "1" else "advanced"
            reference = reply.pick(version)
            print(f"\n  Read this aloud:\n  {paint(reference, 'bold')}\n")

            # 4. Score the pronunciation (retry as often as wanted)
            while True:
                try:
                    audio = record_until_enter(workdir / "you.wav", "Press Enter to START reading")
                    heard = transcriber.transcribe(audio, args.language)
                except RuntimeError as exc:
                    print(paint(f"  {exc}", "red"))
                    break
                print(paint(f"  Heard: {heard.text or '(nothing)'}", "dim"))
                print_result(score_pronunciation(reference, heard.words or heard.text))
                if input("\n  [r] retry  [Enter] next turn > ").strip().lower() != "r":
                    break

            history.append((partner_text, reference))
            if one_shot:
                break
    deck.close()
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    settings = load_settings()
    heard = make_transcriber(settings).transcribe(args.audio, args.language)
    print(paint(f"Heard: {heard.text or '(nothing)'}", "dim"))
    print_result(score_pronunciation(args.text, heard.words or heard.text))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    settings = load_settings()
    deck = VocabDeck(settings.db_path)
    cards = deck.due(limit=args.limit)
    if not cards:
        print(f"Nothing due today. {deck.count()} word(s) in your deck.")
        return 0
    print(f"{len(cards)} word(s) due. Say the word aloud, then check the meaning.\n")
    for card in cards:
        print(f"  {paint(card.word, 'bold')}")
        input("  (Enter to reveal) ")
        print(f"  {card.meaning}")
        if card.example:
            print(paint(f"  “{card.example}”", "dim"))
        raw = input("  How well did you remember? 0 (forgot) – 5 (perfect), q to stop [4] > ").strip().lower()
        if raw == "q":
            break
        quality = int(raw) if raw.isdigit() and 0 <= int(raw) <= 5 else 4
        updated = deck.review(card.word, quality)
        print(paint(f"  Next review: {updated.due.isoformat()}\n", "dim"))
    deck.close()
    return 0


# --------------------------------------------------------------------------- entry point

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="correctme", description="AI speaking coach: read better replies aloud, get scored.")
    parser.add_argument("--version", action="version", version=f"CorrectMe {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("practice", help="listen, get a reply, read it aloud, get scored")
    p.add_argument("--level", choices=list(LEVELS), help="reply difficulty (default from CORRECTME_LEVEL or C2)")
    p.add_argument("--partner-text", help="skip the microphone: type what your partner said")
    p.add_argument("--partner-audio", help="skip the microphone: audio file of your partner")
    p.add_argument("--language", default="en", help="language spoken (default: en)")
    p.set_defaults(func=cmd_practice)

    s = sub.add_parser("score", help="score an audio file against the sentence it should contain")
    s.add_argument("--text", required=True, help="the sentence that was supposed to be read")
    s.add_argument("--audio", required=True, help="audio file with the learner's recording")
    s.add_argument("--language", default="en")
    s.set_defaults(func=cmd_score)

    r = sub.add_parser("review", help="flashcards for collected vocabulary")
    r.add_argument("--limit", type=int, default=20)
    r.set_defaults(func=cmd_review)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (KeyboardInterrupt, EOFError):
        print("\nBye!")
        return 0
    except (ImportError, FileNotFoundError, ValueError) as exc:
        print(paint(f"Error: {exc}", "red"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
