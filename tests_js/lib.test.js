// Run with: node --test "tests_js/*.test.js"
// fixtures.json holds results produced by the Python scoring (core/pronunciation.py),
// so these tests fail if the web version drifts away from the desktop version.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  addCard, addDays, buildSystemPrompt, buildUserPrompt, dueCards, parseReply, ratio, reviewCard,
  scorePronunciation, tokenize, weakWords, whisperToHeard,
} from "../docs/lib.js";

const fixtures = JSON.parse(readFileSync(new URL("./fixtures.json", import.meta.url), "utf8"));

test("similarity ratio matches Python difflib", () => {
  for (const [a, b, expected] of fixtures.pairs) {
    assert.ok(Math.abs(ratio(a, b) - expected) < 1e-12, `ratio(${a}, ${b}) = ${ratio(a, b)}, expected ${expected}`);
  }
});

test("scoring matches the Python implementation", () => {
  for (const c of fixtures.cases) {
    const got = scorePronunciation(c.reference, c.heard);
    assert.deepEqual(got, c.expected, `case: ${c.reference}`);
  }
});

test("tokenize handles punctuation and curly apostrophes", () => {
  assert.deepEqual(tokenize("Hello, World! It's fine."), ["hello", "world", "it's", "fine"]);
  assert.deepEqual(tokenize("don’t"), ["don't"]);
  assert.deepEqual(tokenize(null), []);
});

test("empty reference is rejected, nothing heard scores zero", () => {
  assert.throws(() => scorePronunciation("...", "hello"));
  const r = scorePronunciation("good morning", "");
  assert.equal(r.overall, 0);
  assert.ok(r.words.every((w) => w.status === "missing"));
});

test("weakWords flags low scores", () => {
  const r = scorePronunciation("a thorough analysis", "a through analysis");
  assert.deepEqual(weakWords(r).map((w) => w.reference), ["thorough"]);
});

test("whisper verbose_json becomes per-word confidence", () => {
  const json = {
    text: "good morning",
    words: [{ word: "good", start: 0.1, end: 0.4 }, { word: "morning", start: 0.5, end: 0.9 }],
    segments: [{ start: 0, end: 1, avg_logprob: Math.log(0.8) }],
  };
  const heard = whisperToHeard(json);
  assert.equal(heard.length, 2);
  assert.ok(Math.abs(heard[0].probability - 0.8) < 1e-9);
  assert.deepEqual(whisperToHeard({ text: "hi there" }), [
    { word: "hi", probability: null }, { word: "there", probability: null },
  ]);
});

test("SM-2 intervals grow, forgetting resets, ease has a floor", () => {
  const deck = [];
  assert.equal(addCard(deck, { word: "Candid" }, "2026-11-14"), true);
  assert.equal(addCard(deck, { word: "candid" }, "2026-11-14"), false);
  assert.deepEqual(dueCards(deck, "2026-11-14").map((c) => c.word), ["candid"]);

  const c1 = reviewCard(deck[0], 4, "2026-11-14");
  assert.deepEqual([c1.interval, c1.reps, c1.due], [1, 1, "2026-11-15"]);
  const c2 = reviewCard(c1, 4, c1.due);
  assert.equal(c2.interval, 6);
  const c3 = reviewCard(c2, 4, c2.due);
  assert.equal(c3.interval, 15);
  const forgot = reviewCard(c3, 1, c3.due);
  assert.deepEqual([forgot.reps, forgot.interval], [0, 1]);

  let card = deck[0];
  for (let i = 0; i < 20; i++) card = reviewCard(card, 0, "2026-11-14");
  assert.ok(card.ease >= 1.3);
  assert.throws(() => reviewCard(deck[0], 9));
  assert.equal(addDays("2026-12-30", 3), "2027-01-02");
});

test("prompts and reply parsing", () => {
  assert.match(buildSystemPrompt("C2", "Indonesian"), /IELTS band 9/);
  assert.throws(() => buildSystemPrompt("Z9", "Indonesian"));
  const up = buildUserPrompt("What do you do?", [["Hi", "Hello"], ["How are you?", "Splendid"]]);
  assert.match(up, /Partner: How are you\?/);
  assert.ok(up.endsWith('Partner (just now): "What do you do?"'));

  const out = { natural: "I'd love to.", advanced: "Seldom have I met such an offer.", target_words: [
    { word: "seldom", meaning: "jarang", example: "Seldom seen." }, { word: "", meaning: "ignored" } ] };
  const fenced = "Sure!\n```json\n" + JSON.stringify(out) + "\n```\nDone.";
  const p = parseReply(fenced);
  assert.equal(p.advanced, out.advanced);
  assert.deepEqual(p.targetWords.map((t) => t.word), ["seldom"]);
  assert.deepEqual(parseReply("Just text."), { natural: "Just text.", advanced: "Just text.", targetWords: [] });
  assert.equal(parseReply(JSON.stringify({ natural: "Hello there." })).advanced, "Hello there.");
  assert.throws(() => parseReply("  "));
  assert.throws(() => parseReply("{}"));
});
