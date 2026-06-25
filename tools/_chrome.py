"""
Utilitários para usar o Google Chrome em modo headless como motor de
renderização — tanto para capturar gráficos (HTML -> PNG) quanto para
gerar o relatório (HTML -> PDF).

Optou-se pelo Chrome headless por ser a única ferramenta de conversão
disponível de forma confiável no ambiente (sem depender de wkhtmltopdf,
weasyprint ou LaTeX), além de renderizar CSS moderno e JavaScript
(Chart.js) com alta fidelidade.
"""

from __future__ import annotations

import os
import shutil
import subprocess

# caminhos candidatos do binário do Chrome/Chromium por plataforma
_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]


def find_chrome() -> str:
    """Localiza o binário do Chrome/Chromium. Lança RuntimeError se ausente."""
    env_path = os.getenv("CHROME_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    for candidate in _CHROME_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
        found = shutil.which(candidate)
        if found:
            return found

    raise RuntimeError(
        "Google Chrome/Chromium não encontrado. Instale o Chrome ou defina "
        "a variável de ambiente CHROME_PATH apontando para o binário."
    )


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Chrome headless falhou (código {result.returncode}).\n"
            f"stderr: {result.stderr[-2000:]}"
        )


def html_to_png(
    html_path: str,
    png_path: str,
    width: int = 1100,
    height: int = 640,
    virtual_time_budget_ms: int = 4000,
) -> None:
    """Renderiza um arquivo HTML e captura um screenshot PNG.

    Usa `--virtual-time-budget` para dar tempo ao JavaScript (Chart.js)
    de desenhar antes da captura.
    """
    chrome = find_chrome()
    url = f"file://{os.path.abspath(html_path)}"
    _run([
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--force-device-scale-factor=2",  # PNG em alta resolução (retina)
        f"--window-size={width},{height}",
        f"--virtual-time-budget={virtual_time_budget_ms}",
        f"--screenshot={os.path.abspath(png_path)}",
        url,
    ])


def html_to_pdf(
    html_path: str,
    pdf_path: str,
    virtual_time_budget_ms: int = 5000,
) -> None:
    """Renderiza um arquivo HTML e gera um PDF (respeita @page do CSS)."""
    chrome = find_chrome()
    url = f"file://{os.path.abspath(html_path)}"
    _run([
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",  # remove cabeçalho/rodapé padrão do Chrome
        f"--virtual-time-budget={virtual_time_budget_ms}",
        f"--print-to-pdf={os.path.abspath(pdf_path)}",
        url,
    ])
