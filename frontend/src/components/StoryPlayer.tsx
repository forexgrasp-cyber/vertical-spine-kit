"use client";

import { useEffect, useState } from "react";

interface Beat { h: string; p: string }
interface Story { title: string; subtitle: string; video: string; poster: string; beats: Beat[] }

/**
 * StoryPlayer — movie-like, topic-specific intro for the landing page:
 * branded intro video overlay (skippable) + a pinned 3-beat story section.
 * Reads /brand/story.json generated per project.
 */
export default function StoryPlayer() {
  const [story, setStory] = useState<Story | null>(null);
  useEffect(() => {
    fetch("/brand/story.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => s && setStory(s))
      .catch(() => {});
  }, []);
  if (!story) return null;
  return (
    <>
      <style>{`
        .sb-story{padding:32px 0}
        .sb-story .anim-story-track{height:280vh}
        .sb-story .anim-story-pin{position:sticky;top:40px;min-height:60vh;display:grid;place-items:center;text-align:center}
        .sb-story .anim-story-step{position:absolute;inset:0;display:grid;place-items:center}
        .sb-story .anim-story-step h2{font-size:clamp(1.8rem,4.5vw,3rem);margin:.3rem 0}
        .sb-story .anim-story-step p{color:var(--muted-foreground,#6b7280);max-width:34rem;margin:0 auto}
        .sb-story .anim-story-progress{display:flex;gap:6px}
        .sb-story .anim-story-counter{font:12px ui-monospace,monospace;color:var(--muted-foreground,#6b7280)}
        @media (prefers-reduced-motion:reduce){.sb-story .anim-story-track{height:auto}.sb-story .anim-story-pin{position:relative;min-height:0;padding:40px 0}.sb-story .anim-story-step{position:relative}}
      `}</style>
      <div className="anim-intro" data-max-wait="7">
        <video src={story.video} poster={story.poster} muted playsInline preload="auto" />
        <button className="anim-intro-skip" type="button">Skip ✕</button>
      </div>
      <section className="anim-story sb-story" aria-label={story.title}>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, alignItems: "center" }}>
          <div className="anim-story-progress">
            {story.beats.map((b, i) => (
              <span key={i} className="anim-story-progress-line" />
            ))}
          </div>
          <span className="anim-story-counter">1 / {story.beats.length}</span>
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
    </>
  );
}
