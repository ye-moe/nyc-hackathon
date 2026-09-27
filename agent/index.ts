// src/index.ts
//
// v5: adds a live building-safety check. When a message contains something
// that looks like a street address, the agent queries NYC's own HPD Housing
// Maintenance Code Violations dataset (updated daily) in real time and
// reports open violations for that building — combining the discrimination
// checker with a live "is this building even safe" signal, in one chat.

import { Spectrum, voice } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import { appendFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import os from "node:os";

const app = await Spectrum({
  projectId: process.env.PROJECT_ID,
  projectSecret: process.env.PROJECT_SECRET,
  providers: [imessage.config()],
});

// ---------- regex fallback ----------
const FLAG_PHRASES = [
  /no\s+vouchers?/i,
  /no\s+programs?/i,
  /no\s+section\s*8/i,
  /no\s+cityfheps/i,
  /no\s+housing\s+assistance/i,
  /vouchers?\s+not\s+accepted/i,
  /must\s+not\s+(have|use)\s+(a\s+)?voucher/i,
];

function findIncomeMultiplier(text) {
  const re = /(\d{2,3})\s*(x|times)\b[^.\n]{0,25}?(rent|income|salary)/gi;
  let m;
  const hits = [];
  while ((m = re.exec(text)) !== null) {
    const n = parseInt(m[1], 10);
    if (n) hits.push({ raw: m[0], n });
  }
  return hits;
}

function analyzeWithRegex(text) {
  const flaggedPhrases = FLAG_PHRASES.map((re) => {
    const m = text.match(re);
    return m ? m[0] : null;
  }).filter(Boolean);

  const multiplierHits = findIncomeMultiplier(text).filter((h) => h.n >= 30);
  const isFlagged = flaggedPhrases.length > 0 || multiplierHits.length > 0;

  return {
    verdict: isFlagged ? "violation" : "no_issue_found",
    reasons: [
      ...flaggedPhrases.map((p) => `Exclusionary phrase found: "${p.trim()}"`),
      ...multiplierHits.map((h) => `Income requirement of ~${h.n}x rent excludes voucher holders.`),
    ],
    reasons_en: [
      ...flaggedPhrases.map((p) => `Exclusionary phrase found: "${p.trim()}"`),
      ...multiplierHits.map((h) => `Income requirement of ~${h.n}x rent excludes voucher holders.`),
    ],
    language: "en",
  };
}

// ---------- Gemini (text + image, multilingual) ----------
const GEMINI_KEY = process.env.GEMINI_API_KEY;
const GEMINI_MODEL = process.env.GEMINI_MODEL || "gemini-3.8-flash";

const GEMINI_PROMPT = `You are a housing-discrimination classifier for NYC. You check rental listings (text or a photo of a listing/flyer) for illegal source-of-income discrimination against CityFHEPS voucher holders.

Flag a listing as a violation if it:
- Explicitly refuses vouchers, Section 8, CityFHEPS, or housing assistance (in any language, including paraphrases, euphemisms, or coded language like "no third-party payments")
- Requires income at 30x monthly rent or more applied to the FULL rent (not the tenant's share), which mathematically excludes voucher holders

Do NOT flag: "vouchers welcome," government lottery/AMI listings, or income requirements applied only to a tenant's rent share.

Detect the language the listing itself is written in (if it's an image, read the text in the image first).

Respond with ONLY valid JSON, no markdown, in this exact shape:
{
  "verdict": "violation" | "needs_review" | "no_issue_found",
  "language": "en" | "es" | "bn" | "zh" | "ru" | "other",
  "reasons": ["short reason 1 in the LISTING's language", "short reason 2"],
  "reasons_en": ["same reasons, translated to English, for a caseworker's records"]
}`;

async function callGemini(parts) {
  if (!GEMINI_KEY) return null;
  try {
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_KEY}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ parts }],
          generationConfig: { temperature: 0, responseMimeType: "application/json" },
        }),
      }
    );
    if (!res.ok) {
      console.error("Gemini request failed:", res.status, await res.text());
      return null;
    }
    const data = await res.json();
    const raw = data?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.verdict || !Array.isArray(parsed?.reasons)) return null;
    return parsed;
  } catch (err) {
    console.error("Gemini call threw:", err);
    return null;
  }
}

async function analyzeWithGeminiText(text) {
  const parts = [{ text: GEMINI_PROMPT + "\n\nListing text:\n\"\"\"\n" + text + "\n\"\"\"" }];
  return callGemini(parts);
}

async function analyzeWithGeminiImage(base64, mimeType) {
  const parts = [
    { text: GEMINI_PROMPT + "\n\nThe listing is provided as an image below." },
    { inlineData: { mimeType, data: base64 } },
  ];
  return callGemini(parts);
}

async function analyzeText(text) {
  const result = await analyzeWithGeminiText(text);
  if (result) return { ...result, source: "gemini" };
  console.log("Falling back to regex classifier (Gemini unavailable or failed).");
  return { ...analyzeWithRegex(text), source: "regex" };
}

async function analyzeImage(base64, mimeType) {
  const result = await analyzeWithGeminiImage(base64, mimeType);
  if (result) return { ...result, source: "gemini" };
  return {
    verdict: "needs_review",
    reasons: ["Could not read the image automatically — a caseworker should look at it directly."],
    reasons_en: ["Could not read the image automatically — a caseworker should look at it directly."],
    language: "en",
    source: "none",
  };
}

// ---------- NEW: live building-safety check via NYC HPD violations ----------
const ADDRESS_PATTERN = /\b(\d{1,5}[A-Za-z]?)\s+([A-Za-z0-9](?:[A-Za-z0-9\s.'-]{2,40}?))\s+(St(?:reet)?|Ave(?:nue)?|Rd|Road|Blvd|Boulevard|Pl(?:ace)?|Dr(?:ive)?|Ln|Lane|Ct|Court|Pkwy|Parkway)\b\.?/i;

function extractAddress(text) {
  const m = text.match(ADDRESS_PATTERN);
  if (!m) return null;
  return { houseNumber: m[1], streetName: `${m[2].trim()} ${m[3]}`.trim(), full: m[0].trim() };
}

async function checkBuildingViolations(address) {
  try {
    // NYC's own address data drops ordinal suffixes ("170 STREET", not "170th
    // Street"), so normalize before querying or the search silently misses.
    const normalizedStreet = address.streetName.replace(/\b(\d+)(st|nd|rd|th)\b/gi, "$1");
    const query = encodeURIComponent(`${address.houseNumber} ${normalizedStreet}`);
    const url = `https://data.cityofnewyork.us/resource/wvxf-dwi5.json?$q=${query}&$limit=200`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const rows = await res.json();
    if (!Array.isArray(rows) || rows.length === 0) return { found: false };

    const open = rows.filter((r) => (r.violationstatus || r.currentstatus || "").toLowerCase().includes("open"));
    const hazardous = open.filter((r) => r.class === "B" || r.class === "C");

    return {
      found: true,
      totalOpen: open.length,
      hazardous: hazardous.length,
      sampleDescription: open[0]?.novdescription?.slice(0, 120) || null,
    };
  } catch (err) {
    console.error("HPD violations lookup failed:", err);
    return null;
  }
}

function buildingLine(check) {
  if (!check || check.found === false) return null;
  if (check.totalOpen === 0) return "🏢 Building check: no open HPD violations found for this address.";
  const hazardPart = check.hazardous > 0 ? `, including ${check.hazardous} hazardous (Class B/C)` : "";
  return `🏢 Building check: ${check.totalOpen} open HPD violation(s) found for this address${hazardPart}.`;
}

// ---------- NEW: repeat-offender detection across all past conversations ----------
// The bot's own log becomes a growing memory: if the same contact phone number
// shows up in a previously flagged listing, it surfaces that pattern here —
// intelligence that compounds over time, not a one-off check.
const PHONE_PATTERN = /\(?\b\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/;

function extractPhone(text) {
  const m = text.match(PHONE_PATTERN);
  return m ? m[0].replace(/\D/g, "") : null;
}

async function countPriorFlagsForPhone(phone) {
  try {
    const file = Bun.file(LOG_FILE);
    if (!(await file.exists())) return 0;
    const text = await file.text();
    const lines = text.split("\n").filter(Boolean);
    let count = 0;
    for (const line of lines) {
      try {
        const entry = JSON.parse(line);
        if (entry.phone === phone && entry.verdict === "violation") count++;
      } catch {}
    }
    return count;
  } catch (err) {
    console.error("Repeat-offender lookup failed:", err);
    return 0;
  }
}

function repeatOffenderLine(count) {
  if (count <= 0) return null;
  return `🔁 Pattern alert: this contact number has appeared in ${count} previously flagged listing${count > 1 ? "s" : ""} — possible repeat offender.`;
}

// ---------- NEW: spoken verdict via ElevenLabs — the bot doesn't just text, it talks ----------
// This matters for accessibility (low-literacy or visually impaired tenants)
// as much as it does for "wow" — hearing "this may be illegal" lands
// differently than reading it.
const ELEVEN_KEY = process.env.ELEVENLABS_API_KEY;
const ELEVEN_VOICE_ID = process.env.ELEVENLABS_VOICE_ID || "21m00Tcm4TlvDq8ikWAM"; // "Rachel", a stock multilingual-capable voice

async function synthesizeSpeech(text) {
  if (!ELEVEN_KEY || !text) return null;
  try {
    const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${ELEVEN_VOICE_ID}`, {
      method: "POST",
      headers: { "xi-api-key": ELEVEN_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ text, model_id: "eleven_multilingual_v2" }),
    });
    if (!res.ok) {
      console.error("ElevenLabs request failed:", res.status, await res.text());
      return null;
    }
    const arrayBuffer = await res.arrayBuffer();
    return Buffer.from(arrayBuffer);
  } catch (err) {
    console.error("ElevenLabs call threw:", err);
    return null;
  }
}

async function sendSpokenVerdict(space, spokenText) {
  const audio = await synthesizeSpeech(spokenText);
  if (!audio) return;
  try {
    // Convert to m4a ourselves (rather than relying on Spectrum's internal
    // ffmpeg auto-convert) and send by file path — the documented, most
    // reliable way to get a real native voice bubble instead of a silent one.
    const tmpDir = os.tmpdir();
    const mp3Path = path.join(tmpDir, `verdict-${Date.now()}.mp3`);
    const m4aPath = mp3Path.replace(/\.mp3$/, ".m4a");
    await writeFile(mp3Path, audio);

    const proc = Bun.spawn(["ffmpeg", "-y", "-i", mp3Path, m4aPath], {
      stdout: "ignore",
      stderr: "ignore",
    });
    await proc.exited;

    await space.send(voice(m4aPath));
  } catch (err) {
    console.error("Failed to send voice note:", err);
  }
}

// ---------- localized fixed phrases ----------
const PHRASES = {
  en: {
    violation: "🚫 Likely violation — this listing may discriminate against voucher holders.",
    needsReview: "⚠️ Ambiguous — worth a caseworker's own read before acting.",
    clear: "✅ No known exclusionary language or excessive income multiplier found.",
    askDraft: 'Want me to draft a CHR complaint for this? Reply "yes" and I\'ll prepare it for review.',
    declined: "No problem — let me know if you want it drafted later.",
    onlyCaseworker: "(Only the caseworker in this chat can confirm the draft — reply with your role if this is new: \"I am the caseworker.\")",
  },
  es: {
    violation: "🚫 Posible infracción — este anuncio podría discriminar a titulares de vales de vivienda.",
    needsReview: "⚠️ Ambiguo — vale la pena que un trabajador social lo revise antes de actuar.",
    clear: "✅ No se encontró lenguaje excluyente ni un requisito de ingresos excesivo.",
    askDraft: '¿Quieres que redacte una queja para la CHR? Responde "sí" y la prepararé para revisión.',
    declined: "Sin problema — avísame si quieres que la redacte más tarde.",
    onlyCaseworker: "(Solo el trabajador social en este chat puede confirmar el borrador.)",
  },
  bn: {
    violation: "🚫 সম্ভাব্য লঙ্ঘন — এই বিজ্ঞাপনটি ভাউচারধারীদের প্রতি বৈষম্য করতে পারে।",
    needsReview: "⚠️ অস্পষ্ট — পদক্ষেপ নেওয়ার আগে কেসওয়ার্কারের নিজে দেখা উচিত।",
    clear: "✅ কোনো বর্জনমূলক ভাষা বা অতিরিক্ত আয়ের প্রয়োজনীয়তা পাওয়া যায়নি।",
    askDraft: 'আমি কি এর জন্য একটি অভিযোগের খসড়া তৈরি করব? "হ্যাঁ" বলে উত্তর দিন।',
    declined: "কোনো সমস্যা নেই — পরে দরকার হলে জানাবেন।",
    onlyCaseworker: "(শুধুমাত্র এই চ্যাটের কেসওয়ার্কার খসড়া নিশ্চিত করতে পারবেন।)",
  },
  zh: {
    violation: "🚫 可能违规 — 此房源可能歧视持有租房券的租户。",
    needsReview: "⚠️ 不明确 — 建议个案工作者亲自核实后再采取行动。",
    clear: "✅ 未发现排斥性语言或过高的收入要求。",
    askDraft: "需要我起草一份投诉吗？回复\"是\"，我会准备好供审核。",
    declined: "没问题 — 之后需要的话请告诉我。",
    onlyCaseworker: "（只有此对话中的个案工作者可以确认起草。）",
  },
  ru: {
    violation: "🚫 Возможное нарушение — это объявление может дискриминировать держателей ваучеров.",
    needsReview: "⚠️ Неоднозначно — стоит, чтобы социальный работник сам ознакомился, прежде чем действовать.",
    clear: "✅ Исключающих формулировок или завышенных требований к доходу не найдено.",
    askDraft: "Подготовить жалобу по этому объявлению? Ответьте «да», и я подготовлю её для проверки.",
    declined: "Хорошо — дайте знать, если понадобится позже.",
    onlyCaseworker: "(Подтвердить составление жалобы может только социальный работник в этом чате.)",
  },
};

function phrasesFor(lang) {
  return PHRASES[lang] || PHRASES.en;
}

// ---------- draft ----------
function buildDraft(text, reasonsEn, buildingLineText) {
  const lines = [
    "NYC Commission on Human Rights — Source of Income Discrimination Complaint (Draft)",
    `Date: ${new Date().toLocaleDateString()}`,
    "",
    "Summary of issue:",
    ...reasonsEn.map((r) => `- ${r}`),
  ];
  if (buildingLineText) lines.push("", buildingLineText.replace("🏢 ", ""));
  lines.push(
    "",
    "Listing text as received:",
    `"${text.trim()}"`,
    "",
    "[Caseworker: review before submitting. Nothing is filed automatically.]"
  );
  return lines.join("\n");
}

// ---------- logging ----------
const LOG_DIR = path.join(process.cwd(), "data");
const LOG_FILE = path.join(LOG_DIR, "agent_flagged.jsonl");

async function logFlagged(entry) {
  try {
    await mkdir(LOG_DIR, { recursive: true });
    await appendFile(LOG_FILE, JSON.stringify(entry) + "\n", "utf-8");
  } catch (err) {
    console.error("Failed to log flagged listing:", err);
  }
}

// ---------- listing-signal gate ----------
const LISTING_SIGNAL = /\$\s?\d{3,}|(\bbed(room)?s?\b|\bbath(room)?s?\b|\brent\b|\bavailable\b|\bapt\b|\bsq\.?\s?ft\b)/i;
const URL_PATTERN = /https?:\/\/\S+/i;

function looksLikeListing(text) {
  return LISTING_SIGNAL.test(text) || URL_PATTERN.test(text) || ADDRESS_PATTERN.test(text);
}

// ---------- roles ----------
const rolesBySpace = new Map();
const CASEWORKER_INTRO = /\b(i'?m|i am)\s+the\s+caseworker\b/i;
const CLIENT_INTRO = /\b(i'?m|i am)\s+the\s+client\b/i;

function setRole(spaceId, senderId, role) {
  if (!rolesBySpace.has(spaceId)) rolesBySpace.set(spaceId, new Map());
  rolesBySpace.get(spaceId).set(senderId, role);
}
function getRole(spaceId, senderId) {
  return rolesBySpace.get(spaceId)?.get(senderId);
}
function spaceHasCaseworker(spaceId) {
  const roles = rolesBySpace.get(spaceId);
  if (!roles) return false;
  return [...roles.values()].includes("caseworker");
}

// ---------- per-conversation memory ----------
const pendingBySpace = new Map();
const CONFIRM_WORDS = /^\s*(yes|yep|yeah|go ahead|draft it|do it|please|sí|si|হ্যাঁ|是|да)\s*[.!]?\s*$/i;
const DECLINE_WORDS = /^\s*(no|nah|not now|skip|cancel|না|不|нет)\s*[.!]?\s*$/i;

// ---------- main loop ----------
for await (const [space, message] of app.messages) {
  await space.responding(async () => {
    const senderId = message.sender.id;

    // --- photo handling ---
    if (message.content.type === "attachment") {
      try {
        const bytes = await message.content.read();
        const base64 = bytes.toString("base64");
        const mimeType = message.content.mimeType || "image/jpeg";

        const result = await analyzeImage(base64, mimeType);
        const p = phrasesFor(result.language);

        await logFlagged({
          timestamp: new Date().toISOString(),
          space: space.id,
          verdict: result.verdict,
          reasons_en: result.reasons_en,
          source: result.source,
          type: "image",
        });

        if (result.verdict === "violation") {
          pendingBySpace.set(space.id, { text: "[photo of listing]", reasonsEn: result.reasons_en, language: result.language, buildingLineText: null });
          const lines = [p.violation, ...result.reasons.map((r) => `• ${r}`), "", p.askDraft];
          if (spaceHasCaseworker(space.id)) lines.push(p.onlyCaseworker);
          await message.reply(lines.join("\n"));
          await sendSpokenVerdict(space, `${p.violation} ${result.reasons[0] || ""}`);
        } else if (result.verdict === "needs_review") {
          await message.reply([p.needsReview, ...result.reasons.map((r) => `• ${r}`)].join("\n"));
        } else {
          await message.reply(p.clear);
        }
      } catch (err) {
        console.error("Failed to process image:", err);
        await message.reply("Couldn't read that photo — try sending the listing as text instead.");
      }
      return;
    }

    if (message.content.type !== "text") return;
    const trimmed = message.content.text.trim();
    if (!trimmed) return;

    // --- role assignment ---
    if (CASEWORKER_INTRO.test(trimmed)) {
      setRole(space.id, senderId, "caseworker");
      await message.reply("Got it — noting you as the caseworker for this conversation.");
      return;
    }
    if (CLIENT_INTRO.test(trimmed)) {
      setRole(space.id, senderId, "client");
      await message.reply("Got it — noting you as the client for this conversation.");
      return;
    }

    const pending = pendingBySpace.get(space.id);

    // --- confirm/decline a pending draft ---
    if (pending && CONFIRM_WORDS.test(trimmed)) {
      const senderRole = getRole(space.id, senderId);
      if (spaceHasCaseworker(space.id) && senderRole !== "caseworker") {
        const p = phrasesFor(pending.language);
        await message.reply(p.onlyCaseworker);
        return;
      }
      pendingBySpace.delete(space.id);
      const draft = buildDraft(pending.text, pending.reasonsEn, pending.buildingLineText);
      await message.reply(`Here's the draft:\n\n${draft}\n\n(A human still needs to review and send this.)`);
      return;
    }
    if (pending && DECLINE_WORDS.test(trimmed)) {
      pendingBySpace.delete(space.id);
      const p = phrasesFor(pending.language);
      await message.reply(p.declined);
      return;
    }

    if (!looksLikeListing(trimmed)) return;

    // --- building check runs independently of the discrimination verdict ---
    const address = extractAddress(trimmed);
    const buildingCheck = address ? await checkBuildingViolations(address) : null;
    const buildingLineText = buildingLine(buildingCheck);

    // --- repeat-offender check, based on the bot's own accumulated log ---
    const phone = extractPhone(trimmed);
    const priorFlagCount = phone ? await countPriorFlagsForPhone(phone) : 0;
    const repeatLineText = repeatOffenderLine(priorFlagCount);

    const result = await analyzeText(trimmed);
    const p = phrasesFor(result.language);

    await logFlagged({
      timestamp: new Date().toISOString(),
      space: space.id,
      verdict: result.verdict,
      language: result.language,
      reasons_en: result.reasons_en,
      source: result.source,
      type: "text",
      address: address ? address.full : null,
      building_open_violations: buildingCheck?.totalOpen ?? null,
      phone,
    });

    if (result.verdict === "violation") {
      pendingBySpace.set(space.id, { text: trimmed, reasonsEn: result.reasons_en, language: result.language, buildingLineText });
      const lines = [p.violation, ...result.reasons.map((r) => `• ${r}`)];
      if (buildingLineText) lines.push("", buildingLineText);
      if (repeatLineText) lines.push("", repeatLineText);
      lines.push("", p.askDraft);
      if (spaceHasCaseworker(space.id)) lines.push(p.onlyCaseworker);
      await message.reply(lines.join("\n"));
      await sendSpokenVerdict(space, `${p.violation} ${result.reasons[0] || ""}`);
    } else if (result.verdict === "needs_review") {
      const lines = [p.needsReview, ...result.reasons.map((r) => `• ${r}`)];
      if (buildingLineText) lines.push("", buildingLineText);
      if (repeatLineText) lines.push("", repeatLineText);
      await message.reply(lines.join("\n"));
    } else {
      const lines = [p.clear];
      if (buildingLineText) lines.push("", buildingLineText);
      if (repeatLineText) lines.push("", repeatLineText);
      await message.reply(lines.join("\n"));
    }
  });
}
