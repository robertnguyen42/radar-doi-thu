#!/usr/bin/env python3
"""Ghép web/index.html + data/latest.json -> dist/radar.html (1 file, mở offline hoặc đăng artifact)."""
from pathlib import Path
ROOT = Path(__file__).parent
data = (ROOT / "data" / "latest.json").read_text("utf-8").replace("</", "<\\/")
html = (ROOT / "web" / "index.html").read_text("utf-8").replace("__DATA__", data)
(ROOT / "dist").mkdir(exist_ok=True)
html = html.replace("<title>", '<meta name="robots" content="noindex,nofollow">\n<title>', 1)
(ROOT / "dist" / "radar.html").write_text(html, "utf-8")
(ROOT / "dist" / "index.html").write_text(html, "utf-8")      # GitHub Pages
(ROOT / "dist" / "robots.txt").write_text("User-agent: *\nDisallow: /\n", "utf-8")
print("✓ dist/radar.html", len(html) // 1024, "KB")
