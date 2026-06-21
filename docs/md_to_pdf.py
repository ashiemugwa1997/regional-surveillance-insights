# Converts the project markdown docs to styled PDFs (docs/pdf/).
# Markdown -> HTML (with mermaid + tables) -> PDF via headless Chrome.
# Run: python docs/md_to_pdf.py

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "pdf"
OUT.mkdir(exist_ok=True)

# (source markdown, output pdf name)
DOCS = [
    (ROOT / "README.md", "README.pdf"),
    (ROOT / "docs" / "architecture.md", "architecture.pdf"),
    (ROOT / "docs" / "data_quality_report.md", "data_quality_report.pdf"),
]

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color: #1f2d3d; line-height: 1.5; font-size: 12.5px; }
h1 { color: #0a3d62; font-size: 26px; border-bottom: 3px solid #1e88e5; padding-bottom: 6px; }
h2 { color: #0a3d62; font-size: 19px; margin-top: 26px; border-bottom: 1px solid #e3e8ee; padding-bottom: 4px; }
h3 { color: #0a3d62; font-size: 15px; margin-top: 18px; }
h4 { color: #45525f; font-size: 13.5px; }
a { color: #1e88e5; text-decoration: none; }
code { background: #f0f3f7; padding: 1px 5px; border-radius: 4px; font-size: 11.5px;
       font-family: "SFMono-Regular", Consolas, monospace; }
pre { background: #0f1b2a; color: #e6edf3; padding: 12px 14px; border-radius: 8px;
      overflow-x: auto; font-size: 11px; line-height: 1.45; }
pre code { background: none; color: inherit; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 11.5px; }
th, td { border: 1px solid #d9e0e7; padding: 6px 9px; text-align: left; vertical-align: top; }
th { background: #eef2f7; color: #0a3d62; }
tr:nth-child(even) td { background: #f8fafc; }
blockquote { border-left: 4px solid #1e88e5; margin: 10px 0; padding: 4px 14px; color: #45525f; }
.mermaid { background: #fff; text-align: center; margin: 16px 0; }
h1, h2, h3 { page-break-after: avoid; }
pre, table, .mermaid { page-break-inside: avoid; }
"""

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
</script></head><body>{body}</body></html>"""


def find_chrome():
    for c in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if shutil.which(c):
            return c
    raise RuntimeError("No Chrome/Chromium found for PDF rendering.")


def to_html(md_text):
    # Pull mermaid fences out before markdown processing, restore as <pre class="mermaid">.
    blocks = []

    def stash(m):
        blocks.append(m.group(1))
        return f"@@MERMAID{len(blocks) - 1}@@"

    md_text = re.sub(r"```mermaid\n(.*?)```", stash, md_text, flags=re.DOTALL)
    body = markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "toc", "sane_lists"]
    )
    for i, code in enumerate(blocks):
        body = body.replace(f"<p>@@MERMAID{i}@@</p>", f'<pre class="mermaid">{code}</pre>')
        body = body.replace(f"@@MERMAID{i}@@", f'<pre class="mermaid">{code}</pre>')
    return HTML.format(css=CSS, body=body)


def main():
    chrome = find_chrome()
    for src, out_name in DOCS:
        if not src.exists():
            print(f"skip (missing): {src}")
            continue
        html = to_html(src.read_text())
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tf:
            tf.write(html)
            tmp = tf.name
        out = OUT / out_name
        subprocess.run([
            chrome, "--headless", "--disable-gpu", "--no-sandbox",
            "--no-pdf-header-footer",
            "--virtual-time-budget=10000",
            "--run-all-compositor-stages-before-draw",
            f"--print-to-pdf={out}", f"file://{tmp}",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Path(tmp).unlink(missing_ok=True)
        print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
