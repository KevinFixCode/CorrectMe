// CorrectMe web app. Everything runs in the browser; your key and deck stay on this device.
import {
  LEVELS, WEAK_THRESHOLD, addCard, buildCorrectionSystemPrompt, buildCorrectionUserPrompt, buildSystemPrompt,
  buildUserPrompt, dueCards, parseCorrection, parseReply, reviewCard, scorePronunciation, segmentTranscript,
  weakWords, whisperToHeard,
} from "./lib.js";

// ------------------------------------------------------------------ storage

const DEFAULTS = {
  baseUrl: "https://api.groq.com/openai/v1",
  apiKey: "",
  model: "openai/gpt-oss-120b",
  sttModel: "whisper-large-v3",
  engine: "auto", // auto | browser | whisper
  level: "C2",
  nativeLanguage: "Indonesian",
};

function readJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}
function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

let settings = { ...DEFAULTS, ...readJSON("cm_settings", {}) };
let deck = readJSON("cm_deck", []);
if (!Array.isArray(deck)) deck = [];
const saveSettings = () => writeJSON("cm_settings", settings);
const saveDeck = () => writeJSON("cm_deck", deck);

// ------------------------------------------------------------------ tiny DOM helper

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "text") node.textContent = v;
    else if (k === "ref") v(node);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}
// Model output is untrusted: it is only ever inserted as text, never as HTML.

const view = document.getElementById("view");

// ------------------------------------------------------------------ speech capture

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

function chosenEngine() {
  if (settings.engine === "browser") return SR ? "browser" : "whisper";
  if (settings.engine === "whisper") return "whisper";
  return SR ? "browser" : "whisper";
}

const SPEECH_ERRORS = {
  "not-allowed": "Izin mikrofon ditolak. Izinkan mikrofon untuk situs ini di pengaturan browser.",
  "service-not-allowed": "Pengenalan suara tidak diizinkan di browser ini. Coba mesin Whisper di Pengaturan.",
  "audio-capture": "Mikrofon tidak ditemukan.",
  network: "Pengenalan suara browser butuh internet. Periksa koneksimu.",
  "no-speech": "Tidak ada suara terdengar. Coba lagi, dekatkan mikrofon.",
};

/** Browser speech recognition. stop() resolves with {text, words:null}. */
function browserCapture(onLive) {
  const rec = new SR();
  rec.lang = "en-US";
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;
  let finalText = "";
  let interim = "";
  let error = null;
  let done;
  const finished = new Promise((resolve) => (done = resolve));
  rec.onresult = (e) => {
    interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalText += r[0].transcript + " ";
      else interim += r[0].transcript;
    }
    onLive?.((finalText + interim).trim());
  };
  rec.onerror = (e) => { error = e.error; };
  rec.onend = () => {
    const text = (finalText || interim).trim();
    if (error && !text) done({ error: SPEECH_ERRORS[error] || `Kesalahan suara: ${error}` });
    else done({ text, words: null });
  };
  rec.start();
  return { stop: () => { try { rec.stop(); } catch { /* already stopped */ } return finished; }, finished };
}

/** Records audio and sends it to a Whisper endpoint. stop() resolves with {text, words}. */
async function whisperCapture() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    return { error: "Browser ini tidak bisa merekam suara." };
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    return { error: SPEECH_ERRORS["not-allowed"] };
  }
  const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"]
    .find((t) => MediaRecorder.isTypeSupported?.(t));
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks = [];
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  let done;
  const finished = new Promise((resolve) => (done = resolve));
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    try {
      const type = recorder.mimeType || mimeType || "audio/webm";
      const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      const form = new FormData();
      form.append("file", new Blob(chunks, { type }), `speech.${ext}`);
      form.append("model", settings.sttModel);
      form.append("language", "en");
      form.append("response_format", "verbose_json");
      form.append("timestamp_granularities[]", "word");
      form.append("timestamp_granularities[]", "segment");
      const json = await apiFetch("/audio/transcriptions", { method: "POST", body: form });
      done({ text: (json.text || "").trim(), words: whisperToHeard(json) });
    } catch (err) {
      done({ error: err.message });
    }
  };
  recorder.start();
  return { stop: () => { if (recorder.state !== "inactive") recorder.stop(); return finished; }, finished: null };
}

/** Start capturing with the chosen engine. Returns {stop()} or {error}. */
async function startCapture(onLive) {
  if (chosenEngine() === "browser") return browserCapture(onLive);
  if (!settings.apiKey) return { error: "Mesin Whisper memakai key API. Isi key di Pengaturan." };
  return whisperCapture();
}

// ------------------------------------------------------------------ API calls (OpenAI-compatible)

async function apiFetch(path, init = {}, cfg = settings) {
  const base = cfg.baseUrl.replace(/\/+$/, "");
  const headers = { ...(init.headers || {}) };
  if (cfg.apiKey) headers.Authorization = `Bearer ${cfg.apiKey}`;
  if (typeof init.body === "string") headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(base + path, { ...init, headers });
  } catch {
    throw new Error(
      "Tidak bisa terhubung ke layanan AI.\nPeriksa internet, alamat (Base URL) di Pengaturan, atau apakah layanan mengizinkan akses dari browser."
    );
  }
  const text = await res.text();
  if (!res.ok) {
    let detail = text.slice(0, 300);
    try { detail = JSON.parse(text).error?.message || detail; } catch { /* keep raw text */ }
    const hint =
      res.status === 401 ? "\nKey API salah atau sudah dicabut."
      : res.status === 404 ? "\nNama model salah atau tidak tersedia untuk akunmu. Tekan 'Cek model' di Pengaturan."
      : res.status === 429 ? "\nBatas pemakaian gratis tercapai. Tunggu sebentar lalu coba lagi."
      : "";
    throw new Error(`Permintaan gagal (HTTP ${res.status}): ${detail}${hint}`);
  }
  try { return JSON.parse(text); } catch { throw new Error("Respons layanan AI bukan JSON yang valid."); }
}

async function chat(system, user, temperature) {
  const json = await apiFetch("/chat/completions", {
    method: "POST",
    body: JSON.stringify({
      model: settings.model,
      temperature,
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
    }),
  });
  return json?.choices?.[0]?.message?.content;
}

async function generateReply(partnerText, history) {
  const content = await chat(
    buildSystemPrompt(settings.level, settings.nativeLanguage),
    buildUserPrompt(partnerText, history),
    0.7
  );
  return parseReply(content);
}

async function correctSpeech(text, speaker) {
  const content = await chat(
    buildCorrectionSystemPrompt(settings.nativeLanguage, speaker),
    buildCorrectionUserPrompt(text),
    0.2
  );
  return parseCorrection(content);
}

// ------------------------------------------------------------------ views

const state = {
  tab: "practice",
  step: "partner", // partner | replies | result
  partnerText: "",
  reply: null,
  version: "advanced",
  result: null,
  heardText: "",
  history: [],
  busy: false,
  recording: null, // active capture handle
  live: "",
  message: null, // {kind: 'error'|'notice', text}
  addedWords: 0,
  review: { revealed: false },
  correct: { text: "", speaker: "self", result: null, analyzed: "", loading: false, added: 0 },
};

function go(tab) {
  stopRecordingQuietly();
  state.tab = tab;
  state.message = null;
  render();
}

function stopRecordingQuietly() {
  if (state.recording) {
    state.recording.stop?.();
    state.recording = null;
  }
}

function messageBox() {
  if (!state.message) return null;
  return el("div", { class: state.message.kind === "error" ? "error" : "notice", role: "alert" }, state.message.text);
}

function needsKey() {
  return !settings.apiKey && !/localhost|127\.0\.0\.1/.test(settings.baseUrl);
}

function updateChrome() {
  document.querySelectorAll(".tab").forEach((b) => {
    if (b.dataset.tab === state.tab) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  const due = dueCards(deck).length;
  const pill = document.getElementById("due-count");
  pill.hidden = due === 0;
  pill.textContent = String(due);
  document.getElementById("engine-badge").textContent =
    chosenEngine() === "browser" ? "Suara: browser" : "Suara: Whisper";
}

function render() {
  view.replaceChildren(
    state.tab === "practice" ? renderPractice()
      : state.tab === "correct" ? renderCorrect()
      : state.tab === "deck" ? renderDeck()
      : renderSettings()
  );
  updateChrome();
}

// ---- practice

async function toggleCapture(onDone) {
  if (state.recording) {
    const handle = state.recording;
    state.recording = null;
    state.busy = true;
    render();
    const out = await handle.stop();
    state.busy = false;
    onDone(out);
    return;
  }
  state.message = null;
  const handle = await startCapture((text) => {
    state.live = text;
    const target = document.getElementById("live");
    if (target) target.textContent = text || "…";
  });
  if (handle.error) {
    state.message = { kind: "error", text: handle.error };
    render();
    return;
  }
  state.live = "";
  state.recording = handle;
  render();
  // Browser recognition ends by itself after a pause: finish automatically.
  handle.finished?.then((out) => {
    if (state.recording === handle) {
      state.recording = null;
      onDone(out);
    }
  });
}

function micButton(label, onDone) {
  const recording = !!state.recording;
  return el(
    "button",
    {
      class: `btn block ${recording ? "danger" : ""}`,
      type: "button",
      onclick: () => toggleCapture(onDone),
      disabled: state.busy,
    },
    recording ? [el("span", { class: "recdot" }), "Berhenti"] : label
  );
}

function renderPractice() {
  const box = el("section", {}, messageBox());
  if (needsKey()) {
    box.append(
      el("div", { class: "notice" }, "Isi key API di tab Pengaturan dulu (gratis di console.groq.com), lalu kembali ke sini.")
    );
  }
  if (state.step === "partner") box.append(partnerStep());
  else if (state.step === "replies") box.append(repliesStep());
  else box.append(resultStep());
  return box;
}

function partnerStep() {
  let makeBtn = { disabled: false }; // replaced by the real buttons once they are created
  let fixBtn = { disabled: false };
  const ta = el("textarea", {
    id: "partner",
    placeholder: "Ketik apa kata lawan bicara, atau tekan mikrofon dan biarkan dia berbicara.",
    "aria-label": "Kata lawan bicara",
  });
  ta.value = state.partnerText;
  ta.addEventListener("input", () => {
    state.partnerText = ta.value;
    makeBtn.disabled = state.busy || !ta.value.trim() || !!state.recording;
    fixBtn.disabled = !ta.value.trim() || !!state.recording;
  });

  const mic = micButton(
    "🎙️ Dengarkan lawan bicara",
    (out) => {
      if (out.error) state.message = { kind: "error", text: out.error };
      else if (out.text) state.partnerText = out.text;
      else state.message = { kind: "notice", text: "Tidak ada suara tertangkap. Coba lagi." };
      render();
    }
  );

  return el(
    "div",
    {},
    el("h2", {}, "Apa kata lawan bicara?"),
    ta,
    el("div", { id: "live", class: "live", "aria-live": "polite" }, state.recording ? state.live || "Mendengarkan…" : ""),
    el("div", { class: "row" }, mic),
    el(
      "button",
      {
        class: "btn block",
        type: "button",
        disabled: state.busy || !state.partnerText.trim() || !!state.recording,
        ref: (node) => { makeBtn = node; },
        onclick: async () => {
          state.busy = true;
          state.message = null;
          render();
          try {
            const reply = await generateReply(state.partnerText, state.history);
            state.reply = reply;
            state.version = "advanced";
            state.addedWords = 0;
            for (const t of reply.targetWords) if (addCard(deck, t)) state.addedWords++;
            saveDeck();
            state.step = "replies";
          } catch (err) {
            state.message = { kind: "error", text: err.message };
          }
          state.busy = false;
          render();
        },
      },
      state.busy ? "Menulis balasan…" : "Buat balasan"
    ),
    el("button", {
      class: "btn secondary block",
      type: "button",
      style: "margin-top:10px",
      disabled: !state.partnerText.trim() || !!state.recording,
      ref: (node) => { fixBtn = node; },
      onclick: () => {
        state.correct = { ...state.correct, text: state.partnerText, speaker: "other", result: null };
        go("correct");
      },
    }, "Koreksi kalimat ini"),
    el("p", { class: "muted" }, "Balasan hanya berupa teks. Kamu yang membacanya dengan suara sendiri.")
  );
}

function repliesStep() {
  const r = state.reply;
  const pick = (v) => () => { state.version = v; render(); };
  const option = (v, label) =>
    el(
      "button",
      { class: "card selectable", type: "button", "aria-pressed": String(state.version === v), onclick: pick(v) },
      el("div", { class: "label" }, label),
      el("div", {}, r[v])
    );
  const mic = micButton(
    "🎙️ Baca keras",
    (out) => {
      if (out.error) state.message = { kind: "error", text: out.error };
      else scoreReading(out);
      render();
    }
  );
  return el(
    "div",
    {},
    el("p", { class: "muted" }, r.context ?? `Lawan bicara: “${state.partnerText.trim()}”`),
    option("natural", r.labels?.natural ?? "Natural"),
    option("advanced", r.labels?.advanced ?? "Advanced"),
    r.targetWords.length ? el("h3", {}, "Kata target") : null,
    ...r.targetWords.map((t) =>
      el("div", { class: "target" }, el("b", {}, t.word), t.meaning ? ` — ${t.meaning}` : "",
        t.example ? el("div", { class: "muted" }, `“${t.example}”`) : null)
    ),
    state.addedWords ? el("p", { class: "muted" }, `${state.addedWords} kata baru masuk ke Kartu.`) : null,
    el("div", { id: "live", class: "live", "aria-live": "polite" }, state.recording ? state.live || "Mendengarkan…" : ""),
    el("div", { class: "row" }, mic),
    el("button", { class: "btn secondary block", type: "button", disabled: !!state.recording,
      onclick: () => { state.step = "partner"; state.message = null; render(); } }, "Ganti kata lawan bicara")
  );
}

function scoreReading(out) {
  const reference = state.reply[state.version];
  if (!out.text) {
    state.message = { kind: "notice", text: "Tidak ada suara tertangkap. Coba lagi." };
    return;
  }
  state.heardText = out.text;
  state.result = scorePronunciation(reference, out.words || out.text);
  state.step = "result";
}

function resultStep() {
  const r = state.result;
  const level = r.overall >= 85 ? "ok" : r.overall >= WEAK_THRESHOLD ? "close" : "bad";
  const weak = weakWords(r);
  const chip = (w) => {
    const cls = w.status === "missing" || w.status === "wrong" ? "bad" : w.score < WEAK_THRESHOLD ? "close" : "ok";
    const title = w.heard && w.heard !== w.reference ? `terdengar: ${w.heard}` : w.status === "missing" ? "tidak terdengar" : `${w.score}`;
    return el("span", { class: `w ${cls}`, title }, w.reference);
  };
  return el(
    "div",
    {},
    el("h2", {}, "Hasil pronunciation"),
    el("div", { class: `score ${level}` }, String(r.overall), el("small", {}, " / 100")),
    el("div", { class: "words" }, r.words.map(chip)),
    weak.length
      ? el("p", {}, "Latih lagi: ", el("b", {}, weak.map((w) => w.reference).join(", ")))
      : el("p", {}, "Jelas dan percaya diri. Bagus!"),
    el("details", {}, el("summary", {}, "Yang terdengar"), el("p", { class: "muted" }, state.heardText || "(kosong)"),
      r.extra.length ? el("p", { class: "muted" }, `Kata tambahan: ${r.extra.join(" ")}`) : null),
    el("p", { class: "muted" },
      "Skor ini mengukur apakah pendengar (mesin) memahami tiap kata. Mesin suara cenderung memaafkan aksen, jadi anggap ini panduan, bukan nilai ujian."),
    el("div", { class: "row" },
      el("button", { class: "btn", type: "button", onclick: () => { state.step = "replies"; state.message = null; render(); } }, "Coba lagi"),
      el("button", { class: "btn secondary", type: "button", onclick: () => {
        state.history.push([state.partnerText, state.reply[state.version]]);
        state.partnerText = ""; state.reply = null; state.result = null; state.step = "partner"; render();
      } }, "Giliran berikutnya"))
  );
}

// ---- correction

const ISSUE_LABELS = {
  grammar: "Tata bahasa",
  "word choice": "Pilihan kata",
  collocation: "Kolokasi",
  unnatural: "Kurang natural",
  other: "Lainnya",
};

function practiceCorrected() {
  const c = state.correct;
  const r = c.result;
  state.reply = {
    natural: r.corrected,
    advanced: r.polished,
    targetWords: [],
    labels: { natural: "Versi benar", advanced: "Versi lebih tinggi" },
    context: `Ucapan asli: “${c.analyzed.trim()}”`,
  };
  state.partnerText = c.analyzed;
  state.version = "natural";
  state.result = null;
  state.addedWords = 0;
  state.step = "replies";
  go("practice");
}

function renderCorrect() {
  const c = state.correct;
  let correctBtn = { disabled: false };
  const ta = el("textarea", {
    id: "ctext",
    placeholder: "Ucapkan atau ketik kalimat bahasa Inggris yang ingin dikoreksi.",
    "aria-label": "Teks yang dikoreksi",
  });
  ta.value = c.text;
  ta.addEventListener("input", () => {
    c.text = ta.value;
    correctBtn.disabled = c.loading || !ta.value.trim() || !!state.recording;
  });
  const who = el("select", { id: "speaker", "aria-label": "Siapa yang bicara" },
    el("option", { value: "self" }, "Saya"), el("option", { value: "other" }, "Orang lain"));
  who.value = c.speaker;
  who.addEventListener("change", () => { c.speaker = who.value; render(); });

  const mic = micButton("🎙️ Ucapkan atau rekam", (out) => {
    if (out.error) state.message = { kind: "error", text: out.error };
    else if (out.text) { c.text = out.text; c.result = null; }
    else state.message = { kind: "notice", text: "Tidak ada suara tertangkap. Coba lagi." };
    render();
  });

  const box = el("section", {},
    messageBox(),
    needsKey() ? el("div", { class: "notice" }, "Isi key API di tab Pengaturan dulu.") : null,
    el("h2", {}, "Koreksi ucapan"),
    el("p", { class: "muted" }, "Ucapkan apa saja dalam bahasa Inggris, atau ketik teksnya. Bisa ucapanmu sendiri atau orang lain."),
    el("label", { for: "speaker" }, "Siapa yang bicara?"),
    who,
    c.speaker === "other" ? el("p", { class: "muted" }, "Beri tahu orang itu sebelum merekam suaranya.") : null,
    el("label", { for: "ctext" }, "Ucapan"),
    ta,
    el("div", { id: "live", class: "live", "aria-live": "polite" }, state.recording ? state.live || "Mendengarkan…" : ""),
    el("div", { class: "row" }, mic),
    el("button", {
      class: "btn block",
      type: "button",
      disabled: c.loading || !c.text.trim() || !!state.recording,
      ref: (node) => { correctBtn = node; },
      onclick: async () => {
        c.loading = true;
        c.result = null;
        state.message = null;
        render();
        try {
          const result = await correctSpeech(c.text, c.speaker);
          c.analyzed = c.text;
          c.added = 0;
          for (const t of result.targetWords) if (addCard(deck, t)) c.added++;
          saveDeck();
          c.result = result;
        } catch (err) {
          state.message = { kind: "error", text: err.message };
        }
        c.loading = false;
        render();
      },
    }, c.loading ? "Memeriksa…" : "Koreksi"),
    el("p", { class: "muted" }, "Koreksi ini untuk tata bahasa dan pilihan kata. Pelafalan butuh teks acuan, jadi nilailah lewat tombol latihan baca di bawah hasil.")
  );
  if (c.result) box.append(correctionResult(c));
  return box;
}

function correctionResult(c) {
  const r = c.result;
  const parts = segmentTranscript(c.analyzed, r.issues);
  const out = el("div", {}, el("h3", {}, "Yang terdengar"),
    el("p", { class: "transcript" }, parts.map((p) => (p.issue == null ? p.text : el("mark", { title: `Kesalahan ${p.issue + 1}` }, p.text)))));
  if (r.level) out.append(el("p", { class: "muted" }, `Perkiraan level dari ucapan ini: ${r.level} (kasar, hanya dari satu contoh).`));

  if (!r.issues.length) {
    out.append(el("div", { class: "notice ok-note" }, "Tidak ada kesalahan berarti. Bagus!"));
  } else {
    out.append(el("h3", {}, `${r.issues.length} hal yang perlu diperbaiki`));
    r.issues.forEach((it, i) => out.append(
      el("div", { class: "card issue" },
        el("div", { class: "label" }, `${i + 1}. ${ISSUE_LABELS[it.type] || ISSUE_LABELS.other}`),
        el("div", {}, el("span", { class: "w bad" }, it.original), " → ", el("span", { class: "w ok" }, it.fix)),
        it.explanation ? el("p", { class: "muted" }, it.explanation) : null)
    ));
  }
  out.append(
    el("div", { class: "card" }, el("div", { class: "label" }, "Versi benar"), el("div", {}, r.corrected)),
    r.polished !== r.corrected ? el("div", { class: "card" }, el("div", { class: "label" }, "Versi lebih tinggi"), el("div", {}, r.polished)) : null
  );
  if (r.targetWords.length) {
    out.append(el("h3", {}, "Kata untuk dipelajari"),
      ...r.targetWords.map((t) => el("div", { class: "target" }, el("b", {}, t.word), t.meaning ? ` — ${t.meaning}` : "",
        t.example ? el("div", { class: "muted" }, `“${t.example}”`) : null)),
      c.added ? el("p", { class: "muted" }, `${c.added} kata baru masuk ke Kartu.`) : null);
  }
  out.append(el("div", { class: "row" },
    el("button", { class: "btn", type: "button", onclick: practiceCorrected }, "Latih ucapkan versi yang benar"),
    el("button", { class: "btn secondary", type: "button", onclick: () => { c.text = ""; c.result = null; render(); } }, "Koreksi lagi")));
  return out;
}

// ---- deck

function renderDeck() {
  const due = dueCards(deck);
  const box = el("section", {}, el("h2", {}, "Kartu kata"),
    el("p", { class: "muted" }, `${deck.length} kata di kartu, ${due.length} jatuh tempo hari ini.`));
  if (!due.length) {
    box.append(el("div", { class: "card" }, deck.length ? "Tidak ada kartu jatuh tempo. Kembali lagi besok." : "Belum ada kata. Kata target dari latihan masuk ke sini otomatis."));
  } else {
    const card = due[0];
    const rate = (q) => () => {
      const i = deck.findIndex((c) => c.word === card.word);
      deck[i] = reviewCard(card, q);
      saveDeck();
      state.review.revealed = false;
      render();
    };
    box.append(
      el("div", { class: "card" },
        el("div", { class: "score", style: "font-size:32px" }, card.word),
        state.review.revealed
          ? el("div", {}, el("p", {}, card.meaning || "(tanpa arti)"), card.example ? el("p", { class: "muted" }, `“${card.example}”`) : null)
          : el("p", { class: "muted" }, "Ucapkan kata ini dengan suara keras, lalu cek artinya.")),
      state.review.revealed
        ? el("div", { class: "row" },
            el("button", { class: "btn secondary", type: "button", onclick: rate(1) }, "Lupa"),
            el("button", { class: "btn secondary", type: "button", onclick: rate(3) }, "Sulit"),
            el("button", { class: "btn", type: "button", onclick: rate(4) }, "Bagus"),
            el("button", { class: "btn", type: "button", onclick: rate(5) }, "Mudah"))
        : el("button", { class: "btn block", type: "button", onclick: () => { state.review.revealed = true; render(); } }, "Tampilkan arti")
    );
  }
  if (deck.length) {
    box.append(el("details", {}, el("summary", {}, "Semua kata"),
      ...deck.map((c) => el("div", { class: "target" }, el("b", {}, c.word), c.meaning ? ` — ${c.meaning}` : "",
        el("div", { class: "muted" }, `giliran berikutnya: ${c.due}`)))));
  }
  return box;
}

// ---- settings

function renderSettings() {
  const draft = { ...settings };
  const field = (key, label, attrs = {}) => {
    const input = el("input", { id: `f-${key}`, ...attrs });
    input.value = draft[key] ?? "";
    input.addEventListener("input", () => { draft[key] = input.value.trim(); });
    return [el("label", { for: `f-${key}` }, label), input];
  };
  const select = (key, label, options) => {
    const s = el("select", { id: `f-${key}` }, options.map(([v, t]) => el("option", { value: v }, t)));
    s.value = draft[key];
    s.addEventListener("change", () => { draft[key] = s.value; });
    return [el("label", { for: `f-${key}` }, label), s];
  };
  const models = el("datalist", { id: "models" });
  const status = el("p", { class: "muted", role: "status" });

  const save = () => {
    settings = { ...DEFAULTS, ...draft };
    const ok = saveSettings();
    state.message = ok ? { kind: "notice", text: "Tersimpan." } : { kind: "error", text: "Tidak bisa menyimpan (penyimpanan browser diblokir)." };
    if (ok && !needsKey()) {
      state.tab = "practice";
      state.message = { kind: "notice", text: "Tersimpan. Silakan mulai berlatih." };
    }
    render();
  };

  return el("section", {},
    messageBox(),
    el("h2", {}, "Pengaturan"),
    el("p", { class: "muted" }, "Key API dan kartu katamu hanya disimpan di browser ini, tidak dikirim ke server CorrectMe (tidak ada). Suara dan teks dikirim ke layanan yang kamu pilih."),
    ...field("baseUrl", "Alamat layanan AI (Base URL)", { type: "url", inputmode: "url", autocomplete: "off" }),
    ...field("apiKey", "Key API", { type: "password", autocomplete: "off" }),
    ...field("model", "Model chat", { list: "models", autocomplete: "off", autocapitalize: "off" }),
    models,
    el("div", { class: "row" },
      el("button", { class: "btn secondary", type: "button", onclick: async () => {
        status.textContent = "Mengambil daftar model…";
        try {
          const json = await apiFetch("/models", {}, { ...settings, baseUrl: draft.baseUrl, apiKey: draft.apiKey });
          const ids = (json.data || []).map((m) => m.id).sort();
          models.replaceChildren(...ids.map((id) => el("option", { value: id })));
          status.textContent = `${ids.length} model tersedia. Ketuk kolom Model chat untuk memilih (hindari whisper, guard, tts).`;
        } catch (err) { status.textContent = err.message; }
      } }, "Cek model")),
    status,
    ...select("engine", "Mesin suara", [
      ["auto", "Otomatis (browser, atau Whisper jika tidak didukung)"],
      ["browser", "Browser (gratis, cepat, cenderung memaafkan)"],
      ["whisper", "Whisper lewat key API (lebih ketat, jalan di iPhone)"],
    ]),
    ...field("sttModel", "Model Whisper", { autocomplete: "off", autocapitalize: "off" }),
    ...select("level", "Tingkat balasan", Object.keys(LEVELS).map((k) => [k, k])),
    ...field("nativeLanguage", "Bahasa untuk arti kata", { autocomplete: "off" }),
    el("div", { class: "row" },
      el("button", { class: "btn", type: "button", onclick: save }, "Simpan"),
      el("button", { class: "btn secondary", type: "button", onclick: () => {
        settings = { ...settings, apiKey: "" };
        saveSettings();
        state.message = { kind: "notice", text: "Key dihapus dari browser ini." };
        render();
      } }, "Hapus key")),
    el("p", { class: "muted" }, "Dapatkan key gratis di console.groq.com. Jangan bagikan key-mu ke siapa pun.")
  );
}

// ------------------------------------------------------------------ boot

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => go(b.dataset.tab)));
if (needsKey()) state.tab = "settings";
render();

if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* offline shell is optional */ });
}
