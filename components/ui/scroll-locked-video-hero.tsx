"use client"

import { useEffect, useRef, useState } from "react"

// ─────────────────────────────────────────────────────────────
// Scroll-scrubbed video hero (original by guglielmogiannattasio.exe, 21st.dev).
// For a React/Next.js + shadcn setup; the live site uses the plain-JS port in
// web/shared/hero.js, which behaves the same.
//
// While the hero is on screen, the page is pinned (body position:fixed) and
// wheel/touch/keyboard input drives video.currentTime forward and back.
// Changed from the original, which never released the lock and so made the
// rest of the page unreachable: once the video ends and the user keeps pushing
// forward, the page unlocks and scrolls on; scrolling back to the top re-locks.
// Also adds a "Skip intro" button and skips locking with prefers-reduced-motion.
// ─────────────────────────────────────────────────────────────

export interface MetroHeroProps {
  videoSrc?: string
  title?: string
  scrollHint?: string
  tagline?: string
  signature?: { name: string; url: string } | false
  /** Total input distance (px) needed to scrub the full video. Tune to taste. */
  scrubDistance?: number
  /** Extra forward scroll (px) past the end before the page unlocks. */
  releasePush?: number
  className?: string
  style?: React.CSSProperties
}

const DEFAULT_VIDEO = "https://cdn.21st.dev/assets/mirror/21/21a77eac28eacbb7e142016eefeaa0b4a766619e51113629a3bc6df6af066c0f.mp4"
const DEFAULT_SIGNATURE = { name: "guglielmogiannattasio.exe", url: "https://www.guglielmogiannattasio.it" }
const SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
const COL_BG = "#05070d"
const COL_TEXT = "#f2f4f8"

function clamp(v: number, min: number, max: number) {
  return Math.min(max, Math.max(min, v))
}

export default function MetroHero({
  videoSrc = DEFAULT_VIDEO,
  title = "HOMEWARD NYC",
  scrollHint = "SCROLL",
  tagline = "Every voucher, a way home.",
  signature = DEFAULT_SIGNATURE,
  scrubDistance = 3200,
  releasePush = 140,
  className,
  style,
}: MetroHeroProps) {
  const sectionRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const titleRef = useRef<HTMLDivElement>(null)
  const hintRef = useRef<HTMLDivElement>(null)
  const taglineRef = useRef<HTMLDivElement>(null)
  const progressBarRef = useRef<HTMLDivElement>(null)
  const skipRef = useRef<HTMLButtonElement>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const video = videoRef.current
    const section = sectionRef.current
    if (!video || !section) return

    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches

    let duration = 0
    let rafId = 0
    let target = 0
    let current = 0
    let started = false
    let seeking = false
    let pendingTime: number | null = null
    let locked = false
    let lockedY = 0
    let touchY = 0
    let push = 0

    const onLoadedData = () => {
      duration = video.duration || 0
      setReady(true)
      if (reduceMotion) video.currentTime = duration * 0.92
    }
    video.addEventListener("loadeddata", onLoadedData)

    // iOS Safari won't buffer until playback starts: silent play-then-pause kicks off loading.
    const p = video.play()
    if (p && typeof p.then === "function") p.then(() => video.pause()).catch(() => {})
    else video.pause()

    const onSeeked = () => {
      seeking = false
      if (pendingTime !== null) {
        const t = pendingTime
        pendingTime = null
        seeking = true
        video.currentTime = t
      }
    }
    video.addEventListener("seeked", onSeeked)
    const seekTo = (t: number) => {
      if (seeking) { pendingTime = t; return }
      seeking = true
      video.currentTime = t
    }

    const heroBottom = () => section.getBoundingClientRect().bottom + window.scrollY
    function lock() {
      if (locked) return
      locked = true
      lockedY = window.scrollY
      Object.assign(document.body.style, { position: "fixed", top: `-${lockedY}px`, left: "0", right: "0", width: "100%", height: "100%", overscrollBehavior: "none" })
    }
    function unlock(scrollTo?: number) {
      if (!locked) return
      locked = false
      Object.assign(document.body.style, { position: "", top: "", left: "", right: "", width: "", height: "", overscrollBehavior: "" })
      window.scrollTo(0, scrollTo ?? lockedY)
    }
    const toContent = () => {
      target = current = 1
      push = 0
      unlock(0)
      window.scrollTo({ top: heroBottom(), behavior: reduceMotion ? "auto" : "smooth" })
    }

    // True if the input scrubbed the video (so the page must not move).
    function drive(dy: number) {
      if (!locked) {
        if (window.scrollY <= 1 && dy < 0) lock()
        else return false
      }
      if (target >= 1 && dy > 0) {
        push += dy
        if (push > releasePush) { toContent(); return true }
      } else push = 0
      target = clamp(target + dy / scrubDistance, 0, 1)
      if (target > 0.001) started = true
      return true
    }

    const onWheel = (e: WheelEvent) => { if (drive(e.deltaY)) e.preventDefault() }
    const onTouchStart = (e: TouchEvent) => { touchY = e.touches[0]?.clientY ?? 0 }
    const onTouchMove = (e: TouchEvent) => {
      const y = e.touches[0]?.clientY ?? touchY
      const dy = touchY - y
      touchY = y
      if (drive(dy)) e.preventDefault()
    }
    const KEYS: Record<string, number> = { ArrowDown: 120, PageDown: 600, " ": 600, ArrowUp: -120, PageUp: -600 }
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName ?? ""
      if (!(e.key in KEYS) || /input|textarea|select/i.test(tag)) return
      if (drive(e.key === " " && e.shiftKey ? -600 : KEYS[e.key])) e.preventDefault()
    }
    const skip = skipRef.current
    skip?.addEventListener("click", toContent)

    function frame() {
      current += (target - current) * 0.18
      if (duration > 0) seekTo(current * duration)
      if (videoRef.current) videoRef.current.style.transform = `scale(${1 + current * 0.06})`
      if (titleRef.current) {
        const t = 1 - clamp(current / 0.35, 0, 1)
        titleRef.current.style.opacity = String(t)
        titleRef.current.style.transform = `translateY(${(1 - t) * -24}px) scale(${0.96 + t * 0.04})`
        titleRef.current.style.filter = `blur(${(1 - t) * 10}px)`
      }
      if (hintRef.current) hintRef.current.style.opacity = started ? "0" : "1"
      if (taglineRef.current) {
        const t = clamp((current - 0.82) / 0.18, 0, 1)
        taglineRef.current.style.opacity = String(t)
        taglineRef.current.style.transform = `translateY(${(1 - t) * 20}px) scale(${0.97 + t * 0.03})`
        taglineRef.current.style.filter = `blur(${(1 - t) * 8}px)`
      }
      if (progressBarRef.current) progressBarRef.current.style.transform = `scaleX(${current})`
      rafId = requestAnimationFrame(frame)
    }

    if (reduceMotion) {
      if (titleRef.current) titleRef.current.style.opacity = "0"
      if (taglineRef.current) taglineRef.current.style.opacity = "1"
      if (hintRef.current) hintRef.current.style.opacity = "0"
      return () => {
        video.removeEventListener("loadeddata", onLoadedData)
        video.removeEventListener("seeked", onSeeked)
        skip?.removeEventListener("click", toContent)
      }
    }

    if (window.scrollY <= 1) lock()
    window.addEventListener("wheel", onWheel, { passive: false })
    window.addEventListener("touchstart", onTouchStart, { passive: true })
    window.addEventListener("touchmove", onTouchMove, { passive: false })
    window.addEventListener("keydown", onKey)
    rafId = requestAnimationFrame(frame)

    return () => {
      video.removeEventListener("loadeddata", onLoadedData)
      video.removeEventListener("seeked", onSeeked)
      window.removeEventListener("wheel", onWheel)
      window.removeEventListener("touchstart", onTouchStart)
      window.removeEventListener("touchmove", onTouchMove)
      window.removeEventListener("keydown", onKey)
      skip?.removeEventListener("click", toContent)
      cancelAnimationFrame(rafId)
      unlock()
    }
  }, [scrubDistance, releasePush])

  const centered: React.CSSProperties = {
    position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", pointerEvents: "none",
  }

  return (
    <div
      ref={sectionRef}
      className={className}
      role="region"
      aria-label="Intro video. Scroll or use the arrow keys to play it."
      style={{ position: "relative", height: "100dvh", width: "100%", overflow: "hidden", background: COL_BG, touchAction: "none", ...style }}
    >
      <video
        ref={videoRef}
        src={videoSrc}
        muted
        playsInline
        preload="auto"
        aria-hidden="true"
        style={{
          position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: ready ? 1 : 0,
          transformOrigin: "center center", willChange: "transform", transition: "opacity 0.6s ease", pointerEvents: "none",
          filter: "grayscale(1) contrast(1.05)",
        }}
      />
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none",
        background: "linear-gradient(180deg, rgba(5,7,13,0.35), rgba(5,7,13,0) 30%, rgba(5,7,13,0.15) 70%, rgba(5,7,13,0.55))" }} />

      <div ref={titleRef} style={{ ...centered, padding: "0 6%" }}>
        <span style={{ fontFamily: SANS, fontWeight: 800, fontSize: "clamp(30px, 7vw, 96px)", lineHeight: 1, letterSpacing: "-0.02em",
          color: COL_TEXT, textShadow: "0 4px 30px rgba(0,0,0,0.5)", display: "inline-block", willChange: "transform, filter, opacity" }}>
          {title}
        </span>
      </div>

      {tagline && (
        <div ref={taglineRef} style={{ ...centered, padding: "0 8%", opacity: 0 }}>
          <span style={{ fontFamily: SANS, fontWeight: 700, fontSize: "clamp(20px, 3.4vw, 40px)", lineHeight: 1.2, letterSpacing: "-0.01em",
            color: COL_TEXT, textShadow: "0 4px 24px rgba(0,0,0,0.5)" }}>
            {tagline}
          </span>
        </div>
      )}

      <div ref={hintRef} style={{ position: "absolute", left: "50%", bottom: "clamp(20px, 6vh, 48px)", transform: "translateX(-50%)",
        display: "flex", flexDirection: "column", alignItems: "center", gap: 8, color: "rgba(240,244,248,0.75)", fontFamily: SANS,
        fontSize: "clamp(10px, 1.4vw, 12px)", fontWeight: 600, letterSpacing: "0.3em", transition: "opacity 0.4s ease", pointerEvents: "none" }}>
        <span>{scrollHint}</span>
        <svg width="14" height="18" viewBox="0 0 14 18" aria-hidden="true" style={{ animation: "metro-hero-bounce 1.6s ease-in-out infinite" }}>
          <style>{`@keyframes metro-hero-bounce{0%,100%{transform:translateY(0);opacity:.5}50%{transform:translateY(5px);opacity:1}}`}</style>
          <path d="M7 1 L7 17 M2 12 L7 17 L12 12" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      <button ref={skipRef} type="button" style={{ position: "absolute", top: "clamp(14px, 3vh, 24px)", right: "clamp(14px, 3vw, 28px)", zIndex: 3,
        background: "rgba(5,7,13,0.55)", color: COL_TEXT, border: "1px solid rgba(255,255,255,0.28)", borderRadius: 10, padding: "0 16px",
        minHeight: 40, fontFamily: SANS, fontSize: 12, fontWeight: 600, letterSpacing: "0.12em", cursor: "pointer" }}>
        SKIP INTRO
      </button>

      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 2, background: "rgba(255,255,255,0.12)" }}>
        <div ref={progressBarRef} style={{ height: "100%", width: "100%", transform: "scaleX(0)", transformOrigin: "left center",
          background: "linear-gradient(90deg, rgba(255,255,255,0.5), rgba(255,255,255,0.95))" }} />
      </div>

      {signature && (
        <span style={{ position: "absolute", right: "clamp(12px, 2.5vw, 24px)", bottom: "clamp(10px, 2vw, 18px)", fontFamily: SANS,
          fontWeight: 500, fontSize: "clamp(11px, 1.4vw, 13px)", color: "rgba(220,224,232,0.6)", zIndex: 2 }}>
          Video by{" "}
          <a href={signature.url} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "none" }}>
            {signature.name}
          </a>
        </span>
      )}
    </div>
  )
}
