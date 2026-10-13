#!/usr/bin/env python3
"""Ghép web/index.html + data/latest.json -> dist/radar.html (1 file, mở offline hoặc đăng artifact)."""
from pathlib import Path
ROOT = Path(__file__).parent
data = (ROOT / "data" / "latest.json").read_text("utf-8").replace("</", "<\\/")
html = (ROOT / "web" / "index.html").read_text("utf-8").replace("__DATA__", data)
(ROOT / "dist").mkdir(exist_ok=True)
(ROOT / "dist" / "radar.html").write_text(html, "utf-8")
print("✓ dist/radar.html", len(html) // 1024, "KB")
