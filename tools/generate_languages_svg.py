#!/usr/bin/env python3
"""Render the "Most used languages" donut for this profile README.

The chart is generated inside this repository, so the profile page does not
depend on a third-party card service.  Public instances such as
github-readme-stats are frequently rate limited, and GitHub's image proxy
then serves a broken image.

Usage:
    GITHUB_TOKEN=... python3 tools/generate_languages_svg.py

The numbers are bytes of code per language across the user's own public
repositories.  Repositories listed in EXCLUDED_REPOS are skipped: they only
contain vendored third-party SDK code and would swamp the real numbers.
"""

from __future__ import annotations

import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USERNAME", "WindDevil")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "profile-languages.svg"

# Repositories that are mostly vendored code: counting them would hide the
# languages the profile owner actually writes.
EXCLUDED_REPOS = {
    "Driver_status_detection",
}

# Markup, tooling and data languages that say nothing about the systems work.
HIDDEN_LANGUAGES = {
    "Batchfile",
    "CMake",
    "CSS",
    "DIGITAL Command Language",
    "Dockerfile",
    "HTML",
    "JavaScript",
    "Lex",
    "M4",
    "Makefile",
    "Module Management System",
    "Perl",
    "RPC",
    "Roff",
    "Ruby",
    "Shell",
    "Stylus",
    "TeX",
    "TypeScript",
    "Yacc",
}

# Up to this many languages get their own slice; the rest become "Other".
MAX_SLICES = 4

OTHER_COLOR = "#8b949e"
FALLBACK_COLORS = ["#3572A5", "#dea584", "#f34b7d", "#555555", "#6E4C13"]

# GitHub's linguist colours for the languages this profile can show.
COLORS = {
    "C": "#555555",
    "C++": "#f34b7d",
    "Rust": "#dea584",
    "Python": "#3572A5",
    "Assembly": "#6E4C13",
    "Verilog": "#b2b7f8",
    "SystemVerilog": "#DAE1C2",
    "Cuda": "#3A4E3A",
    "Go": "#00ADD8",
    "Java": "#b07219",
    "Kotlin": "#A97BFF",
    "Scala": "#c22d40",
    "OCaml": "#ef7a08",
    "Haskell": "#5e5086",
    "Zig": "#ec915c",
}

# Keep the same look as the 3D contribution chart it sits next to.
BACKGROUND = "#ffffff"
FOREGROUND = "#00000f"
MUTED = "#57606a"


def api_get(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-languages",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def list_owned_repositories() -> list[str]:
    names: list[str] = []
    page = 1

    while True:
        batch = api_get(
            f"{API}/users/{USERNAME}/repos?per_page=100&type=owner&page={page}"
        )
        if not batch:
            break

        for repo in batch:
            if repo.get("fork"):
                continue
            if repo["name"] in EXCLUDED_REPOS:
                continue
            names.append(repo["name"])

        if len(batch) < 100:
            break
        page += 1

    return names


def collect_language_bytes(repositories: list[str]) -> dict[str, int]:
    totals: dict[str, int] = {}

    for name in repositories:
        languages = api_get(f"{API}/repos/{USERNAME}/{name}/languages")
        for language, size in languages.items():
            if language in HIDDEN_LANGUAGES:
                continue
            totals[language] = totals.get(language, 0) + size

    return totals


def build_slices(totals: dict[str, int]) -> list[dict]:
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    head = ordered[:MAX_SLICES]
    tail = ordered[MAX_SLICES:]

    slices = [{"name": name, "size": size} for name, size in head]
    if tail:
        slices.append({"name": "Other", "size": sum(size for _, size in tail)})

    total = sum(entry["size"] for entry in slices) or 1
    for entry in slices:
        entry["share"] = entry["size"] / total

    return slices


def color_for(name: str, index: int) -> str:
    if name == "Other":
        return OTHER_COLOR
    return COLORS.get(name, FALLBACK_COLORS[index % len(FALLBACK_COLORS)])


def polar(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    radians = math.radians(angle - 90.0)
    return cx + radius * math.cos(radians), cy + radius * math.sin(radians)


def donut_segment(
    cx: float, cy: float, r_out: float, r_in: float, start: float, end: float
) -> str:
    if end - start >= 359.999:
        end = start + 359.999

    x1, y1 = polar(cx, cy, r_out, start)
    x2, y2 = polar(cx, cy, r_out, end)
    x3, y3 = polar(cx, cy, r_in, end)
    x4, y4 = polar(cx, cy, r_in, start)
    large = 1 if end - start > 180.0 else 0

    return (
        f"M {x1:.2f} {y1:.2f} "
        f"A {r_out:.2f} {r_out:.2f} 0 {large} 1 {x2:.2f} {y2:.2f} "
        f"L {x3:.2f} {y3:.2f} "
        f"A {r_in:.2f} {r_in:.2f} 0 {large} 0 {x4:.2f} {y4:.2f} Z"
    )


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render(slices: list[dict], total_bytes: int, generated_at: str) -> str:
    width, height = 880, 260
    cx, cy = 150.0, 130.0
    r_out, r_in = 100.0, 60.0

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Most used languages">',
        f'<rect width="{width}" height="{height}" rx="12" fill="{BACKGROUND}"/>',
    ]

    if len(slices) == 1:
        middle = (r_out + r_in) / 2.0
        parts.append(
            f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{middle:.2f}" fill="none" '
            f'stroke="{color_for(slices[0]["name"], 0)}" '
            f'stroke-width="{r_out - r_in:.2f}"/>'
        )
    else:
        angle = 0.0
        for index, entry in enumerate(slices):
            sweep = entry["share"] * 360.0
            parts.append(
                f'<path d="{donut_segment(cx, cy, r_out, r_in, angle, angle + sweep)}" '
                f'fill="{color_for(entry["name"], index)}"/>'
            )
            angle += sweep

    parts.append(
        f'<text x="{cx:.0f}" y="{cy - 6:.0f}" text-anchor="middle" '
        f'fill="{FOREGROUND}" font-size="20" font-weight="600">'
        f'{total_bytes / 1024 / 1024:.1f} MB</text>'
    )
    parts.append(
        f'<text x="{cx:.0f}" y="{cy + 18:.0f}" text-anchor="middle" '
        f'fill="{MUTED}" font-size="13">of source code</text>'
    )

    legend_x = 320
    legend_y = 60
    row = 30
    for index, entry in enumerate(slices):
        y = legend_y + index * row
        parts.append(
            f'<rect x="{legend_x}" y="{y - 11}" width="12" height="12" rx="3" '
            f'fill="{color_for(entry["name"], index)}"/>'
        )
        parts.append(
            f'<text x="{legend_x + 22}" y="{y}" fill="{FOREGROUND}" '
            f'font-size="15">{escape(entry["name"])}</text>'
        )
        parts.append(
            f'<text x="{width - 40}" y="{y}" fill="{MUTED}" font-size="15" '
            f'text-anchor="end">{entry["share"] * 100:.1f}%</text>'
        )

    parts.append(
        f'<text x="40" y="{height - 18}" fill="{MUTED}" font-size="12">'
        f'public repositories, excluding vendored code · updated {generated_at}</text>'
    )
    parts.append("</svg>")

    return "\n".join(parts) + "\n"


def main() -> int:
    repositories = list_owned_repositories()
    totals = collect_language_bytes(repositories)

    if not totals:
        print("no languages found", file=sys.stderr)
        return 1

    slices = build_slices(totals)
    total_bytes = sum(totals.values())
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    OUTPUT.write_text(render(slices, total_bytes, generated_at), encoding="utf-8")

    print(f"repositories: {len(repositories)}")
    for entry in slices:
        print(f"  {entry['name']:>12}  {entry['share'] * 100:5.1f}%")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as error:
        print(f"GitHub API error: {error.code} {error.reason}", file=sys.stderr)
        raise SystemExit(1)
