"""Generate landing animation assets (shared style_engines package)."""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
SHARED = APP
while SHARED.name != "shared-canonical-services" and SHARED.parent != SHARED:
    SHARED = SHARED.parent
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from shared.style_engines import AnimationOptions, generate_animation_css, generate_animation_js, generate_theme_css  # noqa: E402

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
}


def main() -> int:
    out = APP / "public" / "anim"
    out.mkdir(parents=True, exist_ok=True)
    opts = AnimationOptions.from_dict(dict(PRESET))
    css = generate_theme_css(TOKENS) + "\n" + generate_animation_css(opts)
    js = generate_animation_js(opts)
    (out / "anim.css").write_text(css, encoding="utf-8")
    (out / "anim.js").write_text(js, encoding="utf-8")
    print(f"[+] {out} ({len(css)}B css, {len(js)}B js)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
