"use client";

import { useEffect, useState } from "react";

interface Beat { h: string; p: string }
interface Story { title: string; subtitle: string; video: string; poster: string; motif?: string; beats: Beat[] }

/**
 * LandingShowcase — the movie-like, project-specific showcase block:
 * inline brand video (muted loop, never blocking), animated topic motif,
 * pinned 3-beat story, glowing beats. Data comes from <prefix>/brand/story.json.
 */
export default function LandingShowcase() {
  const [story, setStory] = useState<Story | null>(null);
  useEffect(() => {
    fetch("/brand/story.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => s && setStory(s))
      .catch(() => {});
  }, []);
  if (!story) return null;
  return (
    <section className="anim-story sb-story landing-showcase" aria-label={story.title}>
      <style>{`
        .landing-showcase{position:relative;overflow:hidden;border-radius:24px;margin:24px 0;padding:24px}
        .landing-showcase .sb-video{position:absolute;inset:0;z-index:0}
        .landing-showcase .sb-video video{width:100%;height:100%;object-fit:cover;opacity:.3}
        .landing-showcase .sb-video::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.25),rgba(0,0,0,.65))}
        .landing-showcase > *:not(.sb-video){position:relative;z-index:1}
        .landing-showcase .topic-motif{font-size:3.2rem;display:inline-block;color:var(--anim-primary,#60a5fa)}
        .landing-showcase .anim-story-track{height:280vh}
        .landing-showcase .anim-story-pin{position:sticky;top:40px;min-height:60vh;display:grid;place-items:center;text-align:center}
        .landing-showcase .anim-story-step{position:absolute;inset:0;display:grid;place-items:center}
        .landing-showcase .anim-story-step h2{font-size:clamp(1.8rem,4.5vw,3rem);margin:.3rem 0}
        .landing-showcase .anim-story-step p{max-width:34rem;margin:0 auto;opacity:.85}
        .landing-showcase .anim-story-progress{display:flex;gap:6px}
        .landing-showcase .anim-story-counter{font:12px ui-monospace,monospace;opacity:.7}
        @media (prefers-reduced-motion:reduce){.landing-showcase .sb-video{display:none}.landing-showcase .anim-story-track{height:auto}.landing-showcase .anim-story-pin{position:relative;min-height:0;padding:40px 0}.landing-showcase .anim-story-step{position:relative}}
      `}</style>
      <div className="sb-video" aria-hidden="true">
        <video src={story.video} poster={story.poster} muted autoPlay loop playsInline />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <span className="topic-motif" aria-hidden="true">{story.motif || "✨"}</span>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div className="anim-story-progress">
            {story.beats.map((b, i) => <span key={i} className="anim-story-progress-line" />)}
          </div>
          <span className="anim-story-counter">1 / {story.beats.length}</span>
        </div>
      </div>
      <div className="anim-story-track">
        <div className="anim-story-pin">
          {story.beats.map((b, i) => (
            <div className="anim-story-step" key={i}>
              <div className="anim-story-step-content">
                <h2 className="anim-glow">{b.h}</h2>
                <p>{b.p}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
