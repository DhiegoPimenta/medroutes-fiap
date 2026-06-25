"""
Gera o Relatório Técnico do MedRoutes em HTML e PDF a partir de `RELATORIO.md`.

Fluxo:
    1. Converte o Markdown em HTML (lib `markdown`, com extensões para
       tabelas, blocos de código, HTML embutido e âncoras).
    2. Embute as imagens referenciadas como data URI (base64), tornando o
       HTML autocontido e portável.
    3. Aplica o template + CSS de impressão -> RELATORIO.html.
    4. Renderiza o HTML em PDF com Chrome headless -> RELATORIO.pdf.

Pré-requisito: rodar antes `python experiments/run_experiments.py` e
`python tools/render_chart.py` para que o gráfico exista.

Uso:
    python tools/build_report.py
"""

from __future__ import annotations

import base64
import os
import re
import sys

import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools._chrome import html_to_pdf  # noqa: E402

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
MD_PATH = os.path.join(ROOT, "RELATORIO.md")
HTML_PATH = os.path.join(ROOT, "RELATORIO.html")
PDF_PATH = os.path.join(ROOT, "RELATORIO.pdf")

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}


def _embed_images(html: str) -> str:
    """Substitui src de imagens locais por data URI base64 (HTML autocontido)."""
    def repl(match: re.Match) -> str:
        src = match.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        img_path = os.path.normpath(os.path.join(ROOT, src))
        if not os.path.exists(img_path):
            print(f"[aviso] imagem não encontrada, mantendo src original: {src}")
            return match.group(0)
        ext = os.path.splitext(img_path)[1].lower()
        mime = _MIME.get(ext, "application/octet-stream")
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f'src="data:{mime};base64,{b64}"'

    return re.sub(r'src="([^"]+)"', repl, html)


def build_html() -> str:
    with open(MD_PATH, encoding="utf-8") as f:
        md_text = f.read()

    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "md_in_html", "attr_list", "toc"],
        output_format="html5",
    )
    body = _embed_images(body)

    with open(os.path.join(ASSETS_DIR, "report.css"), encoding="utf-8") as f:
        css = f.read()

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>MedRoutes — Relatório Técnico</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>"""


def main() -> None:
    if not os.path.exists(MD_PATH):
        raise SystemExit(f"{MD_PATH} não encontrado.")

    html = build_html()
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML gerado: {HTML_PATH}")

    html_to_pdf(HTML_PATH, PDF_PATH)
    size_kb = os.path.getsize(PDF_PATH) / 1024
    print(f"PDF gerado:  {PDF_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
