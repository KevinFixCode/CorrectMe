// Pure logic for the CorrectMe web app: scoring, spaced repetition and LLM prompts.
// No DOM access here, so it can be tested with plain Node (see tests_js/).
// The scoring is a port of core/pronunciation.py and must stay in sync with it.

export const LEVELS = {
  B1: "CEFR B1: clear everyday English, simple connectors, common phrasal verbs.",
  B2: "CEFR B2: fluent and fairly precise English, a range of connectors, some idioms.",
  C1:
    "CEFR C1 / IELTS band 7-8: flexible, precise English with less common vocabulary, " +
    "collocations and complex sentence structures.",
  C2:
    "CEFR C2 / IELTS band 9: effortless, idiomatic, highly precise English with " +
    "sophisticated vocabulary and a wide range of complex grammar used naturally.",
};

export const CLOSE_THRESHOLD = 0.6; // similarity at/above this is "close", below is "wrong"
export const WEAK_THRESHOLD = 70; // words scoring under this are flagged for practice
export const FAIL_PENALTY = 10; // points off the overall score per wrong or missing word

// ---------------------------------------------------------------- scoring

/** Python-style round(): halves go to the nearest even number. */
export function pyRound(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (Math.abs(d - 0.5) < 1e-12) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
}

/** Lowercase and split into words, ignoring punctuation (apostrophes are kept). */
export function tokenize(text) {
  const t = String(text ?? "").toLowerCase().replace(/’/g, "'").replace(/‘/g, "'");
  return t.match(/[a-z0-9]+(?:'[a-z0-9]+)*/g) || [];
}

function longestMatch(a, b, b2j, alo, ahi, blo, bhi) {
  let besti = alo;
  let bestj = blo;
  let bestsize = 0;
  let j2len = new Map();
  for (let i = alo; i < ahi; i++) {
    const newj2len = new Map();
    for (const j of b2j.get(a[i]) || []) {
      if (j < blo) continue;
      if (j >= bhi) break;
      const k = (j2len.get(j - 1) || 0) + 1;
      newj2len.set(j, k);
      if (k > bestsize) {
        besti = i - k + 1;
        bestj = j - k + 1;
        bestsize = k;
      }
    }
    j2len = newj2len;
  }
  return [besti, bestj, bestsize];
}

/** Same result as Python's difflib.SequenceMatcher(None, a, b).ratio() for short strings. */
export function ratio(a, b) {
  const total = a.length + b.length;
  if (total === 0) return 1;
  const b2j = new Map();
  for (let j = 0; j < b.length; j++) {
    if (!b2j.has(b[j])) b2j.set(b[j], []);
    b2j.get(b[j]).push(j);
  }
  let matches = 0;
  const queue = [[0, a.length, 0, b.length]];
  while (queue.length) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = longestMatch(a, b, b2j, alo, ahi, blo, bhi);
    if (k) {
      matches += k;
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }
  return (2 * matches) / total;
}

function isClose(a, b) {
  return Math.abs(a - b) <= Math.max(1e-9 * Math.max(Math.abs(a), Math.abs(b)), 1e-9);
}

function align(ref, hyp) {
  const n = ref.length;
  const m = hyp.length;
  const cost = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i++) cost[i][0] = i;
  for (let j = 1; j <= m; j++) cost[0][j] = j;
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      const sub = cost[i - 1][j - 1] + (1 - ratio(ref[i - 1], hyp[j - 1]));
      cost[i][j] = Math.min(sub, cost[i - 1][j] + 1, cost[i][j - 1] + 1);
    }
  }
  const pairs = [];
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && isClose(cost[i][j], cost[i - 1][j - 1] + (1 - ratio(ref[i - 1], hyp[j - 1])))) {
      pairs.push([i - 1, j - 1]);
      i--;
      j--;
    } else if (i > 0 && isClose(cost[i][j], cost[i - 1][j] + 1)) {
      pairs.push([i - 1, null]);
      i--;
    } else {
      pairs.push([null, j - 1]);
      j--;
    }
  }
  return pairs.reverse();
}

function scorePair(similarity, probability) {
  if (similarity >= 0.999) {
    if (probability == null) return [100, "correct"];
    return [pyRound(60 + 40 * Math.min(Math.max(probability, 0), 1)), "correct"];
  }
  if (similarity >= CLOSE_THRESHOLD) return [pyRound(similarity * 70), "close"];
  return [pyRound(similarity * 30), "wrong"];
}

function heardTokens(heard) {
  const tokens = [];
  const probs = [];
  if (typeof heard === "string") {
    for (const t of tokenize(heard)) {
      tokens.push(t);
      probs.push(null);
    }
  } else {
    for (const item of heard || []) {
      for (const t of tokenize(item.word)) {
        tokens.push(t);
        probs.push(item.probability ?? null);
      }
    }
  }
  return [tokens, probs];
}

/**
 * Score how well `heard` matches `reference`.
 * `heard` is a string, or an array of {word, probability} (probability 0-1 or null).
 * Returns {overall, words: [{reference, heard, score, status}], extra: [string]}.
 */
export function scorePronunciation(reference, heard) {
  const ref = tokenize(reference);
  if (ref.length === 0) throw new Error("reference text has no words");
  const [hyp, probs] = heardTokens(heard);

  const words = [];
  const extra = [];
  for (const [ri, hj] of align(ref, hyp)) {
    if (ri === null) extra.push(hyp[hj]);
    else if (hj === null) words.push({ reference: ref[ri], heard: null, score: 0, status: "missing" });
    else {
      const [score, status] = scorePair(ratio(ref[ri], hyp[hj]), probs[hj]);
      words.push({ reference: ref[ri], heard: hyp[hj], score, status });
    }
  }
  const failed = words.filter((w) => w.status === "wrong" || w.status === "missing").length;
  const mean = words.reduce((s, w) => s + w.score, 0) / words.length;
  const overall = Math.max(0, pyRound(mean - FAIL_PENALTY * failed));
  return { overall, words, extra };
}

export function weakWords(result, threshold = WEAK_THRESHOLD) {
  return result.words.filter((w) => w.score < threshold);
}

/**
 * Turn a Whisper `verbose_json` response into [{word, probability}].
 * Confidence is approximated per segment as exp(avg_logprob), because the API gives no per-word probability.
 */
export function whisperToHeard(json) {
  const segments = Array.isArray(json?.segments) ? json.segments : [];
  const segProb = (t) => {
    for (const s of segments) {
      if (t >= s.start - 0.05 && t <= s.end + 0.05 && typeof s.avg_logprob === "number") {
        return Math.min(Math.max(Math.exp(s.avg_logprob), 0), 1);
      }
    }
    return null;
  };
  if (Array.isArray(json?.words) && json.words.length) {
    return json.words.map((w) => ({ word: w.word, probability: segProb(w.start) }));
  }
  return tokenize(json?.text || "").map((word) => ({ word, probability: null }));
}

// ---------------------------------------------------------------- spaced repetition (SM-2)

export function todayISO(d = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function addDays(iso, days) {
  const [y, m, d] = iso.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + days));
  return t.toISOString().slice(0, 10);
}

/** Add a word to the deck array. Returns false if it is already there. */
export function addCard(deck, { word, meaning = "", example = "" }, today = todayISO()) {
  const key = String(word || "").trim().toLowerCase();
  if (!key || deck.some((c) => c.word === key)) return false;
  deck.push({ word: key, meaning, example, ease: 2.5, interval: 0, reps: 0, due: today, added: today });
  return true;
}

export function dueCards(deck, today = todayISO(), limit = 20) {
  return deck
    .filter((c) => c.due <= today)
    .sort((a, b) => (a.due < b.due ? -1 : a.due > b.due ? 1 : a.word < b.word ? -1 : 1))
    .slice(0, limit);
}

/** Record a review (quality 0-5). Returns a new card; below 3 counts as forgotten. */
export function reviewCard(card, quality, today = todayISO()) {
  if (!(quality >= 0 && quality <= 5)) throw new Error("quality must be between 0 and 5");
  let reps;
  let interval;
  if (quality < 3) {
    reps = 0;
    interval = 1;
  } else {
    interval = card.reps === 0 ? 1 : card.reps === 1 ? 6 : pyRound(card.interval * card.ease);
    reps = card.reps + 1;
  }
  const ease = Math.max(1.3, card.ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02));
  return { ...card, ease, interval, reps, due: addDays(today, interval) };
}

// ---------------------------------------------------------------- LLM prompts

export function buildSystemPrompt(level, nativeLanguage) {
  const levelDesc = LEVELS[String(level).toUpperCase()];
  if (!levelDesc) throw new Error(`Unknown level '${level}'. Choose one of: ${Object.keys(LEVELS).join(", ")}`);
  return (
    "You are CorrectMe, an English speaking coach. The learner is a non-native speaker " +
    "who will READ your reply aloud to a real conversation partner, so it must sound " +
    "natural when spoken.\n\n" +
    "Task: given what the conversation partner just said, write replies the learner " +
    "can say back.\n" +
    `Target register: ${levelDesc}\n\n` +
    "Rules:\n" +
    "- Respond to what the partner actually said, directly and in context. Never ignore a question.\n" +
    "- Replies are spoken aloud: 2-3 sentences, no bullet points, no emojis, no stage directions.\n" +
    '- "natural": polished and idiomatic, the way an articulate native speaker would really say it.\n' +
    '- "advanced": the same intent, but showcasing richer vocabulary, precise collocations and one ' +
    "sophisticated grammar structure (for example inversion, a mixed conditional, a cleft sentence " +
    "or a participle clause) without sounding stilted.\n" +
    "- Choose 2-4 target_words that appear verbatim in your replies and are worth learning. " +
    `Give a short meaning in ${nativeLanguage} and a short English example sentence.\n` +
    "- Respond with ONLY a JSON object, no markdown fences, in exactly this shape:\n" +
    '{"natural": "...", "advanced": "...", ' +
    '"target_words": [{"word": "...", "meaning": "...", "example": "..."}]}'
  );
}

export function buildUserPrompt(partnerText, history = []) {
  const lines = [];
  if (history.length) {
    lines.push("Conversation so far:");
    for (const [partner, learner] of history.slice(-4)) {
      lines.push(`Partner: ${partner}`);
      lines.push(`Learner: ${learner}`);
    }
    lines.push("");
  }
  lines.push(`Partner (just now): "${String(partnerText).trim()}"`);
  return lines.join("\n");
}

function extractJson(raw) {
  let text = String(raw ?? "").trim();
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) text = fence[1].trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end <= start) return null;
  try {
    const data = JSON.parse(text.slice(start, end + 1));
    return data && typeof data === "object" && !Array.isArray(data) ? data : null;
  } catch {
    return null;
  }
}

/** Parse the model output into {natural, advanced, targetWords}. Falls back to plain text. */
export function parseReply(raw) {
  const data = extractJson(raw);
  if (data === null) {
    const text = String(raw ?? "").trim();
    if (!text) throw new Error("The language model returned an empty reply.");
    return { natural: text, advanced: text, targetWords: [] };
  }
  let natural = String(data.natural || data.reply || "").trim();
  let advanced = String(data.advanced || "").trim();
  if (!natural && !advanced) throw new Error("The language model reply had no usable text.");
  natural = natural || advanced;
  advanced = advanced || natural;
  const targetWords = [];
  for (const item of Array.isArray(data.target_words) ? data.target_words : []) {
    if (item && typeof item === "object" && String(item.word || "").trim()) {
      targetWords.push({
        word: String(item.word).trim(),
        meaning: String(item.meaning || "").trim(),
        example: String(item.example || "").trim(),
      });
    }
  }
  return { natural, advanced, targetWords };
}

// ---------------------------------------------------------------- speech correction

const ISSUE_TYPES = new Set(["grammar", "word choice", "collocation", "unnatural", "other"]);
const CEFR_LEVELS = new Set(["A1", "A2", "B1", "B2", "C1", "C2"]);

/** Prompt for correcting free speech. `speaker` is "self" (the learner) or "other" (someone else). */
export function buildCorrectionSystemPrompt(nativeLanguage, speaker = "self") {
  const who =
    speaker === "other"
      ? "The speaker is another person, not the user: keep the explanations neutral and factual."
      : "The speaker is the learner: explanations may address them directly.";
  return (
    "You are CorrectMe, an English speaking coach and editor. You receive a speech-to-text " +
    "transcript of something said aloud.\n" +
    `${who}\n\n` +
    "Rules:\n" +
    "- The text comes from speech recognition: ignore punctuation, capitalisation, spacing and filler " +
    "words (um, uh). Never report those.\n" +
    "- Report only genuine mistakes or clearly unnatural phrasing in grammar, word choice, collocation " +
    "and sentence structure. Do not invent errors. If everything is acceptable, return an empty issues list.\n" +
    "- Keep the speaker's meaning. \"original\" must be copied exactly from the transcript (a short span of " +
    "1-6 words). \"fix\" is the corrected replacement for that span. \"type\" is one of: grammar, word choice, " +
    "collocation, unnatural, other.\n" +
    "- \"corrected\" is the full transcript with only the necessary fixes applied. \"polished\" is a more " +
    "sophisticated, natural way to say the same thing (IELTS band 9 style, 1-3 sentences).\n" +
    "- \"level\" is a rough CEFR estimate (A1-C2) based on this sample only.\n" +
    `- Explanations: one or two short sentences in ${nativeLanguage}.\n` +
    "- target_words: 0-3 useful words or collocations from \"polished\" worth learning, each with a short " +
    `meaning in ${nativeLanguage} and a short English example sentence.\n` +
    "- Respond with ONLY a JSON object, no markdown fences, in exactly this shape:\n" +
    '{"corrected": "...", "polished": "...", "level": "B2", ' +
    '"issues": [{"original": "...", "fix": "...", "type": "grammar", "explanation": "..."}], ' +
    '"target_words": [{"word": "...", "meaning": "...", "example": "..."}]}'
  );
}

export function buildCorrectionUserPrompt(transcript) {
  return `Transcript:\n"${String(transcript).trim()}"`;
}

/** Parse the correction JSON. Unlike parseReply there is no plain-text fallback: the result needs structure. */
export function parseCorrection(raw) {
  const data = extractJson(raw);
  if (data === null) throw new Error("The language model did not return the expected JSON.");
  const corrected = String(data.corrected || "").trim();
  const polished = String(data.polished || "").trim();
  if (!corrected && !polished) throw new Error("The language model reply had no usable text.");

  const issues = [];
  for (const item of Array.isArray(data.issues) ? data.issues : []) {
    if (!item || typeof item !== "object") continue;
    const original = String(item.original || "").trim();
    const fix = String(item.fix || "").trim();
    if (!original || !fix || original.toLowerCase() === fix.toLowerCase()) continue;
    const type = String(item.type || "other").trim().toLowerCase();
    issues.push({
      original,
      fix,
      type: ISSUE_TYPES.has(type) ? type : "other",
      explanation: String(item.explanation || "").trim(),
    });
  }
  const targetWords = [];
  for (const item of Array.isArray(data.target_words) ? data.target_words : []) {
    if (item && typeof item === "object" && String(item.word || "").trim()) {
      targetWords.push({
        word: String(item.word).trim(),
        meaning: String(item.meaning || "").trim(),
        example: String(item.example || "").trim(),
      });
    }
  }
  const level = String(data.level || "").trim().toUpperCase();
  return {
    corrected: corrected || polished,
    polished: polished || corrected,
    level: CEFR_LEVELS.has(level) ? level : "",
    issues,
    targetWords,
  };
}

const isWordChar = (ch) => ch !== undefined && /[a-z0-9']/i.test(ch);

/**
 * Split `text` into parts so issues can be highlighted:
 * [{text, issue: index | null}]. Each issue is matched once, case-insensitively, on word boundaries,
 * and overlapping matches are skipped.
 */
export function segmentTranscript(text, issues) {
  const lower = text.toLowerCase();
  const spans = [];
  issues.forEach((it, i) => {
    const needle = String(it.original || "").toLowerCase().trim();
    if (!needle) return;
    let from = 0;
    for (;;) {
      const idx = lower.indexOf(needle, from);
      if (idx === -1) return;
      const end = idx + needle.length;
      const bounded = !isWordChar(lower[idx - 1]) && !isWordChar(lower[end]);
      if (bounded && !spans.some((s) => idx < s.end && end > s.start)) {
        spans.push({ start: idx, end, issue: i });
        return;
      }
      from = idx + 1;
    }
  });
  spans.sort((a, b) => a.start - b.start);
  const parts = [];
  let pos = 0;
  for (const s of spans) {
    if (s.start > pos) parts.push({ text: text.slice(pos, s.start), issue: null });
    parts.push({ text: text.slice(s.start, s.end), issue: s.issue });
    pos = s.end;
  }
  if (pos < text.length) parts.push({ text: text.slice(pos), issue: null });
  return parts;
}
