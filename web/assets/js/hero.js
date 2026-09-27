// Scroll-scrubbed video hero for the homepage. A plain-JS port of the
// "scroll-locked-video-hero" React component (by guglielmogiannattasio.exe),
// so it runs on this site without a build step.
//
// While the hero is on screen, scrolling drives the video forward and back
// instead of moving the page. Differences from the original, which locked the
// page for good (leaving the rest of the homepage unreachable):
//   - once the video ends and the user keeps scrolling, the page unlocks and
//     continues to the content below; scrolling back up to the top re-locks it
//   - keyboard (arrows, Page Up/Down, Space) scrubs too, and a "Skip intro"
//     button jumps straight to the content
//   - with "reduce motion" on, nothing locks: the last frame and text just show
//
// Usage: <div id="hero" data-title="…" data-tagline="…"></div> then MetroHero.mount(el)

const MetroHero = (() => {
  const DEFAULT_VIDEO = "https://cdn.21st.dev/assets/mirror/21/21a77eac28eacbb7e142016eefeaa0b4a766619e51113629a3bc6df6af066c0f.mp4";
  const SIGNATURE = { name: "guglielmogiannattasio.exe", url: "https://www.guglielmogiannattasio.it" };
  const COL_BG = "#05070d", COL_TEXT = "#f2f4f8";
  const RELEASE_PUSH = 140;   // extra scroll (px) past the end of the video before the page unlocks
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  function h(tag, css, attrs = {}) {
    const el = document.createElement(tag);
    Object.assign(el.style, css);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  }

  function mount(root) {
    const opts = {
      videoSrc: root.dataset.video || DEFAULT_VIDEO,
      title: root.dataset.title || "THE CITY OPENS",
      tagline: root.dataset.tagline || "Every door in the city is already open.",
      scrollHint: root.dataset.hint || "SCROLL",
      scrubDistance: Number(root.dataset.scrub || 3200),
    };
    const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ---------- DOM (same structure and styling as the React component) ----------
    Object.assign(root.style, { position: "relative", height: "100dvh", width: "100%", overflow: "hidden", background: COL_BG, touchAction: "none" });
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Intro video. Scroll or use the arrow keys to play it.");

    const video = h("video", { position: "absolute", inset: "0", width: "100%", height: "100%", objectFit: "cover", opacity: "0",
      transformOrigin: "center center", willChange: "transform", transition: "opacity 0.6s ease", pointerEvents: "none",
      filter: "grayscale(1) contrast(1.05)" /* match the site's grayscale theme */ },
      { src: opts.videoSrc, preload: "auto", "aria-hidden": "true" });
    video.muted = true; video.playsInline = true; video.setAttribute("muted", ""); video.setAttribute("playsinline", "");

    const shade = h("div", { position: "absolute", inset: "0", pointerEvents: "none",
      background: "linear-gradient(180deg, rgba(5,7,13,0.35), rgba(5,7,13,0) 30%, rgba(5,7,13,0.15) 70%, rgba(5,7,13,0.55))" });

    const center = css => h("div", Object.assign({ position: "absolute", inset: "0", display: "flex", alignItems: "center",
      justifyContent: "center", textAlign: "center", pointerEvents: "none" }, css));
    const titleWrap = center({ padding: "0 6%" });
    const title = h("p", { margin: "0", fontWeight: "700", fontSize: "clamp(30px, 7vw, 96px)", lineHeight: "1", letterSpacing: "-0.02em",
      color: COL_TEXT, textShadow: "0 4px 30px rgba(0,0,0,0.5)", display: "inline-block", willChange: "transform, filter, opacity" });
    title.textContent = opts.title;
    titleWrap.appendChild(title);

    const tagWrap = center({ padding: "0 8%", opacity: "0" });
    const tag = h("p", { margin: "0", fontWeight: "600", fontSize: "clamp(20px, 3.4vw, 40px)", lineHeight: "1.2", letterSpacing: "-0.01em",
      color: COL_TEXT, textShadow: "0 4px 24px rgba(0,0,0,0.5)" });
    tag.textContent = opts.tagline;
    tagWrap.appendChild(tag);

    const hint = h("div", { position: "absolute", left: "50%", bottom: "clamp(20px, 6vh, 48px)", transform: "translateX(-50%)", display: "flex",
      flexDirection: "column", alignItems: "center", gap: "8px", color: "rgba(240,244,248,0.75)", fontSize: "clamp(10px, 1.4vw, 12px)",
      fontWeight: "600", letterSpacing: "0.3em", transition: "opacity 0.4s ease", pointerEvents: "none" });
    hint.innerHTML = `<span>${opts.scrollHint}</span><svg width="14" height="18" viewBox="0 0 14 18" style="animation:metro-hero-bounce 1.6s ease-in-out infinite" aria-hidden="true"><path d="M7 1 L7 17 M2 12 L7 17 L12 12" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

    const skip = h("button", { position: "absolute", top: "clamp(14px, 3vh, 24px)", right: "clamp(14px, 3vw, 28px)", zIndex: "3",
      background: "rgba(5,7,13,0.55)", color: COL_TEXT, border: "1px solid rgba(255,255,255,0.28)", borderRadius: "10px",
      padding: "0 16px", minHeight: "40px", fontSize: "12px", fontWeight: "600", letterSpacing: "0.12em", cursor: "pointer",
      backdropFilter: "blur(4px)" }, { type: "button" });
    skip.textContent = "SKIP INTRO";

    const track = h("div", { position: "absolute", left: "0", right: "0", bottom: "0", height: "2px", background: "rgba(255,255,255,0.12)" });
    const bar = h("div", { height: "100%", width: "100%", background: "linear-gradient(90deg, rgba(255,255,255,0.5), rgba(255,255,255,0.95))",
      transform: "scaleX(0)", transformOrigin: "left center" });
    track.appendChild(bar);

    const sig = h("span", { position: "absolute", right: "clamp(12px, 2.5vw, 24px)", bottom: "clamp(10px, 2vw, 18px)", fontWeight: "500",
      fontSize: "clamp(11px, 1.4vw, 13px)", color: "rgba(220,224,232,0.6)", zIndex: "2" });
    sig.innerHTML = `Video by <a href="${SIGNATURE.url}" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:none">${SIGNATURE.name}</a>`;

    const style = document.createElement("style");
    style.textContent = "@keyframes metro-hero-bounce{0%,100%{transform:translateY(0);opacity:.5}50%{transform:translateY(5px);opacity:1}}";
    root.append(style, video, shade, titleWrap, tagWrap, hint, skip, track, sig);

    // ---------- behavior ----------
    let duration = 0, rafId = 0, target = 0, current = 0, started = false;
    let seeking = false, pendingTime = null, locked = false, lockedY = 0, touchY = 0, push = 0;

    video.addEventListener("loadeddata", () => {
      duration = video.duration || 0;
      video.style.opacity = "1";
      if (reduceMotion) video.currentTime = duration * 0.92;
    });
    // iOS Safari won't buffer until playback starts: silent play-then-pause kicks off loading.
    const p = video.play();
    if (p && p.then) p.then(() => video.pause()).catch(() => {}); else video.pause();

    video.addEventListener("seeked", () => {
      seeking = false;
      if (pendingTime !== null) { const t = pendingTime; pendingTime = null; seeking = true; video.currentTime = t; }
    });
    const seekTo = t => { if (seeking) { pendingTime = t; return; } seeking = true; video.currentTime = t; };

    const heroBottom = () => root.getBoundingClientRect().bottom + window.scrollY;
    function lock() {
      if (locked) return;
      locked = true; lockedY = window.scrollY;
      Object.assign(document.body.style, { position: "fixed", top: `-${lockedY}px`, left: "0", right: "0", width: "100%", height: "100%", overscrollBehavior: "none" });
    }
    function unlock(scrollTo) {
      if (!locked) return;
      locked = false;
      Object.assign(document.body.style, { position: "", top: "", left: "", right: "", width: "", height: "", overscrollBehavior: "" });
      window.scrollTo(0, scrollTo ?? lockedY);
    }
    const toContent = () => { target = current = 1; push = 0; unlock(0); window.scrollTo({ top: heroBottom(), behavior: reduceMotion ? "auto" : "smooth" }); };

    // Returns true if the input was used to scrub (and the page must not move).
    function drive(dy) {
      if (!locked) {
        // Scrolling back up at the very top re-enters the hero.
        if (window.scrollY <= 1 && dy < 0) { lock(); } else return false;
      }
      if (target >= 1 && dy > 0) {
        push += dy;
        if (push > RELEASE_PUSH) { toContent(); return true; }
      } else push = 0;
      target = clamp(target + dy / opts.scrubDistance, 0, 1);
      if (target > 0.001) started = true;
      return true;
    }

    const onWheel = e => { if (drive(e.deltaY)) e.preventDefault(); };
    const onTouchStart = e => { touchY = e.touches[0] ? e.touches[0].clientY : 0; };
    const onTouchMove = e => {
      const y = e.touches[0] ? e.touches[0].clientY : touchY;
      const dy = touchY - y; touchY = y;
      if (drive(dy)) e.preventDefault();
    };
    const KEYS = { ArrowDown: 120, PageDown: 600, " ": 600, ArrowUp: -120, PageUp: -600 };
    const onKey = e => {
      if (!(e.key in KEYS) || /input|textarea|select/i.test((e.target && e.target.tagName) || "")) return;
      if (drive(e.key === " " && e.shiftKey ? -600 : KEYS[e.key])) e.preventDefault();
    };
    skip.addEventListener("click", toContent);

    function frame() {
      current += (target - current) * 0.18;
      if (duration > 0) seekTo(current * duration);
      video.style.transform = `scale(${1 + current * 0.06})`;
      const t1 = 1 - clamp(current / 0.35, 0, 1);
      titleWrap.style.opacity = String(t1);
      titleWrap.style.transform = `translateY(${(1 - t1) * -24}px) scale(${0.96 + t1 * 0.04})`;
      titleWrap.style.filter = `blur(${(1 - t1) * 10}px)`;
      hint.style.opacity = started ? "0" : "1";
      const t2 = clamp((current - 0.82) / 0.18, 0, 1);
      tagWrap.style.opacity = String(t2);
      tagWrap.style.transform = `translateY(${(1 - t2) * 20}px) scale(${0.97 + t2 * 0.03})`;
      tagWrap.style.filter = `blur(${(1 - t2) * 8}px)`;
      bar.style.transform = `scaleX(${current})`;
      rafId = requestAnimationFrame(frame);
    }

    if (reduceMotion) {
      // No locking or scrubbing: show the end state and let the page scroll normally.
      titleWrap.style.opacity = "0"; tagWrap.style.opacity = "1"; hint.style.opacity = "0"; bar.style.transform = "scaleX(1)";
      root.style.touchAction = "";
      return;
    }
    if (window.scrollY <= 1) lock();
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("keydown", onKey);
    rafId = requestAnimationFrame(frame);
  }

  return { mount };
})();
