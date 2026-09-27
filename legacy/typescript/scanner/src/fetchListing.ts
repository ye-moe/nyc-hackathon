// Turn a listing URL into text (+ screenshot) for /core.
// Primary: jev-ultrafast browser agent (handles JS pages, "See more", pop-ups).
// Fallback: plain HTTP fetch + tag stripping, so a missing key or a jev
// failure never breaks the agent or the demo.

import { join } from "node:path";

export type FetchedListing = {
  url: string;
  title?: string;
  text: string;
  screenshotB64?: string;
  screenshotMediaType?: string;
  via: "jev" | "http";
  steps?: { kind: string; label?: string }[];
  stopped?: string | null;
  elapsedMs: number;
  jevError?: string;
};

const JEV_DIR = process.env.JEV_DIR; // path to a local clone of browser-use/jev-ultrafast
const SIDECAR = join(import.meta.dir, "..", "jev", "fetch_listing.py");
const JEV_TIMEOUT_MS = Number(process.env.JEV_TIMEOUT_MS ?? 45000);

export async function fetchListing(url: string): Promise<FetchedListing> {
  let jevError: string | undefined;
  if (JEV_DIR) {
    try {
      return await viaJev(url);
    } catch (e) {
      jevError = String(e);
    }
  } else {
    jevError = "JEV_DIR not set";
  }
  return { ...(await viaHttp(url)), jevError };
}

async function viaJev(url: string): Promise<FetchedListing> {
  const proc = Bun.spawn(
    ["uv", "run", "--project", JEV_DIR!, "--env-file", join(JEV_DIR!, ".env"), "python", SIDECAR, url],
    { stdout: "pipe", stderr: "pipe" },
  );
  const timer = setTimeout(() => proc.kill(), JEV_TIMEOUT_MS);
  const out = await new Response(proc.stdout).text();
  clearTimeout(timer);
  await proc.exited;
  const lastLine = out.trim().split("\n").pop() ?? "";
  const r = JSON.parse(lastLine || "{}");
  if (!r.ok) throw new Error(r.error ?? `jev exited ${proc.exitCode}`);
  return {
    url: r.url, title: r.title, text: r.text,
    screenshotB64: r.screenshot_b64, screenshotMediaType: r.screenshot_media_type,
    via: "jev", steps: r.steps, stopped: r.stopped, elapsedMs: r.elapsed_ms,
  };
}

async function viaHttp(url: string): Promise<FetchedListing> {
  const t0 = performance.now();
  const res = await fetch(url, {
    headers: { "user-agent": "Mozilla/5.0 (voucher-detector research; read-only)" },
    signal: AbortSignal.timeout(15000),
  });
  const html = await res.text();
  const title = html.match(/<title[^>]*>([^<]*)<\/title>/i)?.[1]?.trim();
  const text = html
    .replace(/<(script|style|noscript)[\s\S]*?<\/\1>/gi, " ")
    .replace(/<br\s*\/?>|<\/(p|div|li|h\d)>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&#39;|&apos;/g, "'").replace(/&quot;/g, '"')
    .replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n").trim();
  return { url: res.url || url, title, text, via: "http", elapsedMs: Math.round(performance.now() - t0) };
}
