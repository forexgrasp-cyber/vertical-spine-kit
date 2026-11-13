"use client";

import { useEffect, useState } from "react";

interface Beat { h: string; p: string }
interface Story { title: string; subtitle: string; video: string; poster: string; motif?: string; beats: Beat[] }

/**
 * LandingShowcase - project-specific showcase block for the landing page:
 * inline brand video (muted loop, never a blocking overlay), animated topic
 * motif, and a sequential beat story driven by the shared .anim-story engine.
 * Beats scroll in normal flow so each ScrollTrigger fires in order (stacking
 * them absolutely made every beat trigger at the same scroll position and
 * overlap). Data: <prefix>/brand/story.json.
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
    <section className="anim-story landing-showcase" aria-label={story.title}>
      <style>{`
        .landing-showcase{position:relative;overflow:hidden;border-radius:24px;margin:24px 0;padding:24px;background:rgba(127,127,127,.06)}
        .landing-showcase .sb-video{position:absolute;inset:0;z-index:0}
        .landing-showcase .sb-video video{width:100%;height:100%;object-fit:cover;opacity:.3}
        .landing-showcase .sb-video::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.25),rgba(0,0,0,.65))}
        .landing-showcase > *:not(.sb-video){position:relative;z-index:1}
        .landing-showcase .sb-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
        .landing-showcase .topic-motif{font-size:3.2rem;display:inline-block;line-height:1;color:var(--anim-primary,#60a5fa)}
        .landing-showcase .anim-story-pin{position:relative;min-height:0}
        .landing-showcase .anim-story-step{min-height:64vh}
        .landing-showcase .anim-story-step h2{font-size:clamp(1.8rem,4.5vw,3rem);margin:.3rem 0}
        .landing-showcase .anim-story-step p{max-width:34rem;margin:0 auto;opacity:.85}
        @media (prefers-reduced-motion:reduce){
          .landing-showcase .sb-video{display:none}
          .landing-showcase .anim-story-step{min-height:0;padding:28px 0}
          .landing-showcase .anim-story-step-content{opacity:1;transform:none}
        }
      `}</style>
      <div className="sb-video" aria-hidden="true">
        <video src={story.video} poster={story.poster} muted autoPlay loop playsInline />
      </div>
      <div className="sb-head">
        <span className="topic-motif" aria-hidden="true">{story.motif || "✨"}</span>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div className="anim-story-progress">
            {story.beats.map((b, i) => <span key={i} className="anim-story-progress-line" />)}
          </div>
          <span className="anim-story-counter">1 / {story.beats.length}</span>
        </div>
      </div>
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
    </section>
  );
}
