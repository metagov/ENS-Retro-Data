"""Capture screenshots of every challenge/hypothesis page and compile into a PDF.

The PDF is intended for the OpenAI vector store so the ChatKit agent has
visual + textual context for every dashboard view.

Flow:
1. Read dashboards/config.yaml for the challenge/hypothesis structure.
2. Launch Playwright headless Chromium, open the live dashboard.
3. For each challenge: click its segmented-control button.
   For each hypothesis: click its button, wait for render, screenshot.
4. Compile all screenshots into a single PDF with rich text metadata
   (challenge, hypothesis, verdict, description, takeaway) so the vector
   store's text extraction produces meaningful embeddings.

Usage:
    python3 scripts/capture_dashboard_screenshots.py [--url URL]

Default URL: https://ensretro.metagov.org/
"""

import argparse
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image as RLImage,
    PageBreak,
    KeepTogether,
)
from PIL import Image as PILImage

REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "dashboards" / "config.yaml"
EXPORT_DIR = REPO_ROOT / "docs" / "vector-store-exports"
PDF_PATH = EXPORT_DIR / "auto__dashboard_visual_atlas.pdf"

DEFAULT_URL = "https://ensretro.metagov.org/"


@dataclass
class ChartMeta:
    challenge_id: str
    challenge_title: str
    challenge_description: str
    hyp_id: str
    hyp_title: str
    hyp_verdict: str
    hyp_description: str
    visuals: list[dict]
    screenshot_path: Path | None = None


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def build_targets(config: dict) -> list[ChartMeta]:
    targets = []
    for ch in config["challenges"]:
        for h in ch["hypotheses"]:
            targets.append(
                ChartMeta(
                    challenge_id=ch["id"],
                    challenge_title=ch["title"],
                    challenge_description=(ch.get("description") or "").strip(),
                    hyp_id=h["id"],
                    hyp_title=h["title"],
                    hyp_verdict=h.get("verdict", ""),
                    hyp_description=(h.get("description") or "").strip(),
                    visuals=h.get("visuals") or [],
                )
            )
    return targets


def capture_screenshots(url: str, config: dict, out_dir: Path) -> list[ChartMeta]:
    targets = build_targets(config)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = context.new_page()

        print(f"Loading {url} ...")
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        current_challenge = None
        for i, t in enumerate(targets, 1):
            print(f"[{i}/{len(targets)}] {t.challenge_id} {t.hyp_id} — {t.hyp_title}")

            # Navigate to challenge if it changed
            if t.challenge_id != current_challenge:
                short = get_challenge_short_title(config, t.challenge_id)
                try:
                    page.get_by_role("radio", name=short, exact=True).click(timeout=10000)
                except Exception:
                    # Fallback: click by text
                    page.get_by_text(short, exact=True).first.click(timeout=10000)
                page.wait_for_timeout(3000)
                current_challenge = t.challenge_id

            # Click hypothesis segmented control
            hyp_short = get_hyp_short_title(config, t.challenge_id, t.hyp_id)
            try:
                page.get_by_role("radio", name=hyp_short, exact=True).click(timeout=10000)
            except Exception:
                try:
                    page.get_by_text(hyp_short, exact=True).first.click(timeout=10000)
                except Exception as e:
                    print(f"   ! Could not click hypothesis '{hyp_short}': {e}")

            # Wait for charts to render — Plotly emits svg + canvas; Streamlit spinners disappear
            page.wait_for_timeout(4500)
            try:
                page.wait_for_selector("text=Key takeaway", timeout=8000)
            except PWTimeout:
                pass  # Some pages have no takeaway (e.g., explorer pages)

            # Full-page screenshot
            out_path = out_dir / f"{t.challenge_id}_{t.hyp_id.replace('.', '_')}.png"
            try:
                page.screenshot(path=str(out_path), full_page=True)
                t.screenshot_path = out_path
                print(f"   ✓ Saved {out_path.name}")
            except Exception as e:
                print(f"   ! Screenshot failed: {e}")

        context.close()
        browser.close()

    return targets


def get_challenge_short_title(config: dict, challenge_id: str) -> str:
    for ch in config["challenges"]:
        if ch["id"] == challenge_id:
            return ch["short_title"]
    return challenge_id


def get_hyp_short_title(config: dict, challenge_id: str, hyp_id: str) -> str:
    for ch in config["challenges"]:
        if ch["id"] == challenge_id:
            for h in ch["hypotheses"]:
                if h["id"] == hyp_id:
                    return h["short_title"]
    return hyp_id


# ---------------------------------------------------------------------------
# PDF assembly
# ---------------------------------------------------------------------------

VERDICT_LABELS = {
    "supported": "Supported",
    "mixed": "Mixed Evidence",
    "rejected": "Not Supported",
    "in_development": "In Development",
    "explorer": "Data Explorer",
}


def _fit_image(path: Path, max_w: float, max_h: float) -> RLImage:
    """Scale screenshot to fit within max dimensions."""
    with PILImage.open(path) as im:
        iw, ih = im.size
    scale = min(max_w / iw, max_h / ih)
    return RLImage(str(path), width=iw * scale, height=ih * scale)


def build_pdf(targets: list[ChartMeta], out_path: Path) -> None:
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="ENS Retro — Dashboard Visual Atlas",
        author="Metagov Research",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "h1", parent=styles["Heading1"],
        fontSize=20, leading=24, textColor=colors.HexColor("#1A202C"),
        spaceAfter=6,
    )
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"],
        fontSize=15, leading=19, textColor=colors.HexColor("#2D3748"),
        spaceAfter=4,
    )
    h3 = ParagraphStyle(
        "h3", parent=styles["Heading3"],
        fontSize=12, leading=16, textColor=colors.HexColor("#4A5568"),
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "body", parent=styles["BodyText"],
        fontSize=10, leading=13, textColor=colors.HexColor("#2D3748"),
        spaceAfter=6,
    )
    takeaway = ParagraphStyle(
        "takeaway", parent=styles["BodyText"],
        fontSize=10, leading=13, textColor=colors.HexColor("#1A365D"),
        backColor=colors.HexColor("#EBF4FF"),
        borderColor=colors.HexColor("#3B4EC8"),
        borderWidth=0.5,
        borderPadding=6,
        spaceBefore=6,
        spaceAfter=10,
    )
    verdict_style = ParagraphStyle(
        "verdict", parent=styles["BodyText"],
        fontSize=10, leading=13, textColor=colors.HexColor("#742A2A"),
        fontName="Helvetica-Bold",
        spaceAfter=8,
    )

    story = []

    # Cover
    story.append(Paragraph("ENS DAO Governance Retrospective", h1))
    story.append(Paragraph("Dashboard Visual Atlas", h2))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "This document captures every challenge, hypothesis, and visualization "
        "from the ENS Retrospective Dashboard (ensretro.metagov.org). Each page "
        "pairs a screenshot of the live chart with its metadata — challenge "
        "context, hypothesis statement, verdict, description, and the "
        "one-line takeaway — so agents and readers have both visual and "
        "textual context for every finding.",
        body,
    ))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Source: <b>github.com/metagov/ENS-Retro-Data</b> · "
        "Live dashboard: <b>ensretro.metagov.org</b>",
        body,
    ))
    story.append(PageBreak())

    # Table of contents
    story.append(Paragraph("Contents", h1))
    story.append(Spacer(1, 8))
    current = None
    for t in targets:
        if t.challenge_id != current:
            story.append(Paragraph(
                f"<b>{t.challenge_id} — {t.challenge_title}</b>",
                body,
            ))
            current = t.challenge_id
        story.append(Paragraph(
            f"&nbsp;&nbsp;&nbsp;&nbsp;{t.hyp_id} — {t.hyp_title}",
            body,
        ))
    story.append(PageBreak())

    # One page per hypothesis
    current = None
    for t in targets:
        if t.challenge_id != current:
            # Challenge divider
            story.append(Paragraph(
                f"{t.challenge_id} — {t.challenge_title}",
                h1,
            ))
            story.append(Paragraph(t.challenge_description.replace("\n", " "), body))
            story.append(Spacer(1, 10))
            current = t.challenge_id

        # Hypothesis header
        story.append(Paragraph(f"{t.hyp_id} — {t.hyp_title}", h2))
        verdict_label = VERDICT_LABELS.get(t.hyp_verdict, t.hyp_verdict.title())
        story.append(Paragraph(f"Verdict: {verdict_label}", verdict_style))

        # Description
        if t.hyp_description:
            story.append(Paragraph(t.hyp_description.replace("\n", " "), body))

        # Visual titles + takeaways (the text that will be embedded)
        for v in t.visuals:
            title = v.get("title", "")
            takeaway_text = (v.get("takeaway") or "").strip().replace("\n", " ")
            if title:
                story.append(Paragraph(f"Chart: {title}", h3))
            if takeaway_text:
                story.append(Paragraph(
                    f"<b>Key takeaway:</b> {takeaway_text}",
                    takeaway,
                ))

        # Screenshot
        if t.screenshot_path and t.screenshot_path.exists():
            img = _fit_image(t.screenshot_path, max_w=170 * mm, max_h=230 * mm)
            story.append(Spacer(1, 6))
            story.append(img)

        story.append(PageBreak())

    doc.build(story)
    print(f"\nPDF built: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--screenshots-only", action="store_true")
    parser.add_argument("--pdf-only", action="store_true",
                        help="Use existing screenshots in _tmp/ and skip browser")
    args = parser.parse_args()

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = EXPORT_DIR / "_screenshots_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    config = load_config()

    if args.pdf_only:
        targets = build_targets(config)
        for t in targets:
            path = tmp_dir / f"{t.challenge_id}_{t.hyp_id.replace('.', '_')}.png"
            if path.exists():
                t.screenshot_path = path
    else:
        print(f"Capturing screenshots from {args.url}")
        targets = capture_screenshots(args.url, config, tmp_dir)

    if args.screenshots_only:
        print(f"Screenshots saved to {tmp_dir}")
        return

    print("\nBuilding PDF...")
    build_pdf(targets, PDF_PATH)
    print(f"Done. PDF at {PDF_PATH}")


if __name__ == "__main__":
    main()
