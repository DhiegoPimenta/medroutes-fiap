"""
Gera o gráfico de convergência do Algoritmo Genético (`convergence.png`) a
partir do `experiments/results/convergence.json`.

Em vez de matplotlib (incompatível com o Python 3.14 do ambiente e com o
pin de numpy do projeto), o gráfico é desenhado com Chart.js e capturado
pelo Chrome headless — o mesmo motor usado para gerar o PDF do relatório.

Uso:
    python tools/render_chart.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys_path_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, sys_path_root)

from tools._chrome import html_to_png  # noqa: E402

RESULTS_DIR = os.path.join(sys_path_root, "experiments", "results")
CONVERGENCE_JSON = os.path.join(RESULTS_DIR, "convergence.json")
OUTPUT_PNG = os.path.join(RESULTS_DIR, "convergence.png")
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# cores das curvas (uma por configuração), na ordem do JSON
LINE_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed"]


def build_chart_html(convergence: dict) -> str:
    """Monta o HTML com Chart.js que desenha as curvas de convergência."""
    configs = convergence["configs"]
    scenario = convergence.get("scenario", {})

    labels = list(range(scenario.get("num_generations", 0) or
                        len(next(iter(configs.values()))["curve"])))

    datasets = []
    for i, (name, data) in enumerate(configs.items()):
        color = LINE_COLORS[i % len(LINE_COLORS)]
        datasets.append({
            "label": name,
            "data": data["curve"],
            "borderColor": color,
            "backgroundColor": color,
            "borderWidth": 2,
            "pointRadius": 0,
            "tension": 0.15,
        })

    with open(os.path.join(ASSETS_DIR, "chart.umd.min.js"), encoding="utf-8") as f:
        chart_js = f.read()

    num_seeds = scenario.get("num_seeds", "?")
    title = f"Convergência do Algoritmo Genético (média de {num_seeds} sementes, escala log)"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 0; background: #ffffff; }}
  #wrap {{ padding: 24px; box-sizing: border-box;
           font-family: -apple-system, Segoe UI, Roboto, sans-serif; }}
</style>
<script>{chart_js}</script>
</head>
<body>
  <div id="wrap"><canvas id="chart" width="1040" height="560"></canvas></div>
  <script>
    const ctx = document.getElementById('chart').getContext('2d');
    new Chart(ctx, {{
      type: 'line',
      data: {{
        labels: {json.dumps(labels)},
        datasets: {json.dumps(datasets, ensure_ascii=False)}
      }},
      options: {{
        animation: false,
        responsive: false,
        plugins: {{
          title: {{ display: true, text: {json.dumps(title, ensure_ascii=False)},
                    font: {{ size: 17 }}, padding: {{ bottom: 16 }} }},
          legend: {{ position: 'bottom',
                     labels: {{ font: {{ size: 11 }}, boxWidth: 24, padding: 12 }} }}
        }},
        scales: {{
          x: {{ title: {{ display: true, text: 'Geração' }},
                ticks: {{ maxTicksLimit: 13 }} }},
          y: {{ type: 'logarithmic',
                title: {{ display: true, text: 'Melhor fitness (menor = melhor, log)' }} }}
        }}
      }}
    }});
  </script>
</body>
</html>"""


def main() -> None:
    if not os.path.exists(CONVERGENCE_JSON):
        raise SystemExit(
            f"{CONVERGENCE_JSON} não encontrado. "
            "Rode antes: python experiments/run_experiments.py"
        )

    with open(CONVERGENCE_JSON, encoding="utf-8") as f:
        convergence = json.load(f)

    html = build_chart_html(convergence)

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html)
        tmp_path = tmp.name

    try:
        html_to_png(tmp_path, OUTPUT_PNG, width=1090, height=620)
        print(f"Gráfico de convergência salvo em: {OUTPUT_PNG}")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    main()
