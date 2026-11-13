"""Generate landing animation assets (shared style_engines package). v3-bare-js

Writes anim.css + anim.js (BARE js — no <script> wrappers, so it parses as an
external file) into the framework's static dir, plus brand video + story JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
# Deterministically find THIS checkout: walking up from a sibling project
# never passes through shared-canonical-services (projects are siblings, not
# children), which used to fall through to site-packages -- where an older
# installed wheel silently shadowed the repo (15 project topics vs 19).
_CANDIDATES = [APP, *APP.parents, Path(r"C:/Users/IhorLeshchuk/PycharmProjects/shared-canonical-services")]
SHARED = next((p for p in _CANDIDATES if p.name == "shared-canonical-services"), _CANDIDATES[-1])
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from shared.style_engines import AnimationOptions, generate_animation_css, generate_animation_js, generate_theme_css  # noqa: E402

# Flask apps serve static from <pkg>/static at /static; everyone else uses public/ at /.
FLASK = (APP / "app.py").is_file() or any((APP / "travel_alerts").is_dir() for _ in [0])
STATIC_DIR = None
for cand in ["travel_alerts/web/static", "web/static", "static", "public"]:
    if (APP / cand).is_dir():
        STATIC_DIR = APP / cand
        break
if STATIC_DIR is None:
    STATIC_DIR = APP / "public"
STATIC_PREFIX = "/static" if str(STATIC_DIR).replace("\\", "/").endswith("/static") else ""

TOKENS = {
    "background_color": "rgb(255, 255, 255)",
    "text_color": "rgb(17, 24, 39)",
    "link_color": "rgb(79, 70, 229)",
    "heading_color": "rgb(17, 24, 39)",
    "font_family": "Inter, system-ui, sans-serif",
    "color_palette": ["rgb(255,255,255)", "rgb(17,24,39)", "rgb(79,70,229)", "rgb(16,185,129)", "rgb(100,116,139)"],
}
PRESET = {
    "level": "premium", "gsap_enabled": True, "split_scrub": True, "text_fade_blur": True,
    "clip_reveal": True, "reveal_group": True, "marquee": True, "counting_number": True,
    "cursor_marquee": True, "btn_hover_fill": True, "glow": True, "tilt_3d": True,
    "scroll_read": True, "wipe_mask": True, "scroll_progress_ring": True, "progressive_blur": True,
    "parallax_intensity": 0.3, "reduced_motion": "respect",
    "intro_video": False,  # NO blocking overlay — video is embedded inline instead
    "pinned_storytelling": True,
}


def main() -> int:
    anim_dir = STATIC_DIR / "anim"
    brand_dir = STATIC_DIR / "brand"
    anim_dir.mkdir(parents=True, exist_ok=True)
    brand_dir.mkdir(parents=True, exist_ok=True)
    opts = AnimationOptions.from_dict(dict(PRESET))
    css = generate_theme_css(TOKENS) + "\n" + generate_animation_css(opts)
    js = generate_animation_js(opts, inline=False)  # bare JS: safe as external file
    (anim_dir / "anim.css").write_text(css, encoding="utf-8")
    (anim_dir / "anim.js").write_text(js, encoding="utf-8")
    print(f"[+] {anim_dir} ({len(css)}B css, {len(js)}B js) prefix={STATIC_PREFIX or '/'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
