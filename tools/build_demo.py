"""Bundle the React UI into one self-contained HTML file (demo/kurs-demo.html),
plus a full-document copy at index.html for GitHub Pages.

The demo swaps the backend API client for demo/api.demo.js and compiles JSX in
the browser with Babel, so it opens without npm or a running backend.
Usage: python tools/build_demo.py
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

app = (SRC / "App.jsx").read_text(encoding="utf-8")
app = re.sub(r"^import .*?;\n", "", app, flags=re.M)
app = app.replace("export default function App", "function App")
css = (SRC / "styles.css").read_text(encoding="utf-8")
api = (ROOT / "demo" / "api.demo.js").read_text(encoding="utf-8")

html = f"""<title>Kurs конвертер</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Manrope:wght@400;500;600;700&family=Unbounded:wght@500;700&display=swap">
<style>
{css}
</style>
<div id="root"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.2/babel.min.js"></script>
<script type="text/babel" data-presets="react">
const {{ useEffect, useMemo, useRef, useState, useCallback }} = React;
{api}
{app}
ReactDOM.createRoot(document.getElementById("root")).render(<App />);
</script>
"""

out = ROOT / "demo" / "kurs-demo.html"
out.write_text(html, encoding="utf-8")
print(f"wrote {out} ({len(html) // 1024} KB)")

# Full document for GitHub Pages (the artifact host adds its own skeleton, Pages does not).
page = (
    '<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="UTF-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    + html.replace('<div id="root">', '</head>\n<body>\n<div id="root">', 1)
    + "</body>\n</html>\n"
)
index = ROOT / "index.html"
index.write_text(page, encoding="utf-8")
print(f"wrote {index}")
