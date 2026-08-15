"""Пересборка HTML-методички из ARTICLE_TEAM_TRAINING.md.

Запуск: python planogram3d/webapp/tools/build_article_html.py
Встраивает скриншоты docs/img как base64 и исходник MD дословно.
"""
# рендер через mdview + журнальный CSS + base64-скриншоты + исходник MD
import base64
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from planogram3d.webapp.mdview import md_to_html  # noqa: E402

DOCS = Path(__file__).resolve().parents[2] / "docs"
md_source = (DOCS / "ARTICLE_TEAM_TRAINING.md").read_text(encoding="utf-8")
body = md_to_html(md_source)

# картинки → data URI (самодостаточный файл)
def embed(match):
    src = match.group(1)
    p = DOCS / src
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f'src="data:image/jpeg;base64,{b64}"'

body = re.sub(r'src="(img/[^"]+)"', embed, body)

# первый h1 уезжает в hero
m = re.search(r"<h1>(.*?)</h1>", body, re.S)
title = m.group(1)
body = body.replace(m.group(0), "", 1)

CSS = """
  :root { --navy:#1d2b3a; --blue:#2f6fed; --ink:#23303f;
          --muted:#5b6672; --light:#f4f6f9; }
  * { box-sizing:border-box; }
  body { margin:0; background:#fbfbf9; color:var(--ink);
         font:16px/1.7 Georgia,'Times New Roman',serif; }
  .hero { background:var(--navy); color:#fff; padding:58px 24px 50px; }
  .hero .in, main, footer .in { max-width:800px; margin:0 auto; }
  .hero .kicker { font:700 12px/1 'Segoe UI',sans-serif;
    letter-spacing:2.5px; text-transform:uppercase; color:#ffd54f; }
  .hero h1 { font-size:36px; line-height:1.25; margin:14px 0 12px; }
  .hero .lead { font-size:16.5px; color:#c8d4e2; font-style:italic;
                line-height:1.6; }
  main { padding:36px 24px 20px; }
  main h2 { font-size:26px; margin:46px 0 14px; line-height:1.25; }
  main h3 { font-size:19px; margin:30px 0 8px; }
  main p { margin:0 0 15px; }
  main ul { margin:0 0 15px; padding-left:26px; }
  main li { margin-bottom:5px; }
  main img { max-width:100%; border-radius:12px; border:1px solid #e0e4ea;
    box-shadow:0 4px 18px rgba(20,40,70,.10); margin:10px 0 2px; }
  main img + em, main p em:only-child { display:block;
    font:12.5px 'Segoe UI',sans-serif; color:var(--muted);
    margin:4px 0 8px; }
  main table { border-collapse:collapse; width:100%; margin:16px 0 20px;
    font:13.5px/1.5 'Segoe UI',sans-serif; }
  main th, main td { border:1px solid #e0e4ea; padding:7px 11px;
    text-align:left; vertical-align:top; }
  main th { background:var(--light); font-size:12.5px; }
  main code { background:#eef1f5; border-radius:4px; padding:1px 6px;
    font-size:13.5px; }
  main pre { background:#141d28; color:#dce6f2; border-radius:10px;
    padding:14px 18px; overflow-x:auto; font:13px/1.6 'Courier New',
    monospace; }
  main pre code { background:none; padding:0; color:inherit; }
  main hr { border:none; border-top:1px solid #e0e4ea; margin:28px 0; }
  main a { color:var(--blue); }
  details.mdsrc { margin:46px 0 10px; font-family:'Segoe UI',sans-serif; }
  details.mdsrc summary { cursor:pointer; font-weight:700;
    font-size:15px; background:var(--navy); color:#fff; padding:12px 18px;
    border-radius:12px; list-style:none; }
  details.mdsrc summary::before { content:"📄 "; }
  details.mdsrc[open] summary { border-radius:12px 12px 0 0; }
  .mdtools { display:flex; gap:8px; background:#141d28; padding:9px 14px; }
  .mdtools button { border:0; border-radius:8px; padding:7px 14px;
    font:600 12.5px 'Segoe UI',sans-serif; cursor:pointer;
    background:var(--blue); color:#fff; }
  .mdtools .hint { margin-left:auto; align-self:center; font-size:11.5px;
    color:#8fa3b8; }
  pre#mdsrc { margin:0; background:#141d28; color:#dce6f2;
    padding:16px 20px 22px; border-radius:0 0 12px 12px;
    overflow-x:auto; font:12.5px/1.6 'Courier New',monospace;
    white-space:pre-wrap; }
  footer { padding:22px 24px 46px; }
  footer .in { border-top:1px solid #e0e4ea; padding-top:16px;
    font:12.5px 'Segoe UI',sans-serif; color:var(--muted); }
  @media print { .mdtools { display:none; } }
"""

page = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Смена как игра — методичка по обучению команды магазина</title>
<style>{CSS}</style>
</head>
<body>
<div class="hero"><div class="in">
  <div class="kicker">Методичка · planogram3d</div>
  <h1>{title}</h1>
  <div class="lead">Педагогические основания, устройство тренажёра,
  программа из трёх модулей с поурочными планами, рубрики оценивания,
  работа наставника и организация занятий — со скриншотами работающей
  системы.</div>
</div></div>
<main>
{body}
<details class="mdsrc">
  <summary>Исходник методички в Markdown (ARTICLE_TEAM_TRAINING.md)</summary>
  <div class="mdtools">
    <button onclick="copyMd()">📋 Копировать</button>
    <button onclick="downloadMd()">⬇ Скачать .md</button>
    <span class="hint">встроен дословно — файл самодостаточен</span>
  </div>
  <pre id="mdsrc">{html.escape(md_source, quote=False)}</pre>
</details>
</main>
<footer><div class="in">planogram3d · методичка командного обучения ·
скриншоты сняты с работающей демо-системы · исходник в Markdown — в
блоке выше</div></footer>
<script>
function mdText() {{ return document.getElementById("mdsrc").textContent; }}
function copyMd() {{
  navigator.clipboard.writeText(mdText()).then(
    () => alert("Markdown скопирован в буфер обмена"));
}}
function downloadMd() {{
  const blob = new Blob([mdText()],
    {{type: "text/markdown;charset=utf-8"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ARTICLE_TEAM_TRAINING.md";
  a.click();
  URL.revokeObjectURL(a.href);
}}
</script>
</body>
</html>
"""

out_path = DOCS / "ARTICLE_TEAM_TRAINING.html"
out_path.write_text(page, encoding="utf-8")
assert html.escape(md_source, quote=False) in page
imgs = page.count("data:image/jpeg;base64")
print(f"OK: {out_path.stat().st_size // 1024} КБ, "
      f"встроено картинок: {imgs}, markdown дословно: да")
