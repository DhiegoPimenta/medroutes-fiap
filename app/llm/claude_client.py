"""
Integracao com a API da Anthropic (Claude) para gerar conteudo em
linguagem natural a partir das rotas otimizadas pelo Algoritmo Genetico.

Funcionalidades:
    - Instrucoes detalhadas de entrega para cada motorista.
    - Relatorio de eficiencia da rota (distancia, tempo estimado, economia
      em relacao a uma rota aleatoria/nao otimizada).
    - Respostas a perguntas em linguagem natural sobre as rotas.

A ANTHROPIC_API_KEY e lida exclusivamente de variavel de ambiente (nunca
hardcoded), seguindo a restricao de seguranca do projeto.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.genetic.fitness import VehicleRoute
from app.models.delivery import DepotLocation

DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeClientError(Exception):
    """Lancado quando a chamada a API da Anthropic falha ou a chave nao existe."""


@dataclass
class RouteEfficiencyMetrics:
    """Metricas resumidas usadas para compor prompts de relatorio/instrucoes."""

    total_distance_km: float
    random_baseline_distance_km: float
    num_vehicles_used: int
    num_deliveries: int
    num_critical_deliveries: int
    estimated_time_hours: float

    @property
    def distance_savings_km(self) -> float:
        return max(0.0, self.random_baseline_distance_km - self.total_distance_km)

    @property
    def distance_savings_percent(self) -> float:
        if self.random_baseline_distance_km <= 0:
            return 0.0
        return (self.distance_savings_km / self.random_baseline_distance_km) * 100


class ClaudeClient:
    """Cliente fino sobre o SDK `anthropic`, isolando o restante do app da API.

    Isolar as chamadas aqui permite mockar facilmente em testes (sem exigir
    chave de API real) e centralizar tratamento de erros/timeouts.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self._client = None  # inicializado de forma lazy em _get_client()

    def _get_client(self):
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise ClaudeClientError(
                "ANTHROPIC_API_KEY nao configurada. Defina a variavel de "
                "ambiente antes de usar funcionalidades de IA generativa."
            )

        try:
            import anthropic
        except ImportError as error:
            raise ClaudeClientError(
                "Biblioteca 'anthropic' nao instalada. Rode `poetry install`."
            ) from error

        self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _send_prompt(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        client = self._get_client()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as error:  # erro generico do SDK da Anthropic
            raise ClaudeClientError(f"Falha ao chamar a API da Anthropic: {error}") from error

        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )

    def generate_driver_instructions(
        self, route: VehicleRoute, depot: DepotLocation
    ) -> str:
        """Gera instrucoes detalhadas em linguagem natural para um motorista."""
        stops_description = "\n".join(
            f"{i+1}. {d.label} - {d.weight_kg:.1f}kg - "
            f"{'MEDICAMENTO CRITICO' if d.is_critical else 'Insumo regular'}"
            for i, d in enumerate(route.deliveries)
        )
        system_prompt = (
            "Voce e um assistente de logistica que escreve instrucoes claras, "
            "objetivas e amigaveis para motoristas de entrega de medicamentos "
            "e insumos hospitalares. Responda em portugues do Brasil."
        )
        user_prompt = (
            f"Gere instrucoes de entrega para o motorista do {route.vehicle.label}.\n"
            f"Ponto de partida: {depot.address}.\n"
            f"Paradas na ordem definida (NAO reordene):\n{stops_description}\n\n"
            "Inclua: ordem das paradas, atencao especial para itens criticos "
            "(entregar com prioridade e cuidado), e um lembrete de retornar ao deposito."
        )
        return self._send_prompt(system_prompt, user_prompt)

    def generate_efficiency_report(self, metrics: RouteEfficiencyMetrics) -> str:
        """Gera relatorio de eficiencia comparando a rota otimizada a uma rota aleatoria."""
        system_prompt = (
            "Voce e um analista de logistica que resume metricas de eficiencia "
            "de roteamento de forma clara para gestores nao tecnicos. "
            "Responda em portugues do Brasil."
        )
        user_prompt = (
            "Resuma a eficiencia da rota otimizada com base nestas metricas:\n"
            f"- Distancia total otimizada: {metrics.total_distance_km:.1f} km\n"
            f"- Distancia de uma rota aleatoria (baseline): {metrics.random_baseline_distance_km:.1f} km\n"
            f"- Economia: {metrics.distance_savings_km:.1f} km ({metrics.distance_savings_percent:.1f}%)\n"
            f"- Veiculos utilizados: {metrics.num_vehicles_used}\n"
            f"- Total de entregas: {metrics.num_deliveries} (sendo {metrics.num_critical_deliveries} criticas)\n"
            f"- Tempo estimado de execucao: {metrics.estimated_time_hours:.1f} horas\n\n"
            "Escreva um paragrafo executivo destacando o ganho de eficiencia "
            "e a importancia de priorizar as entregas criticas."
        )
        return self._send_prompt(system_prompt, user_prompt)

    def answer_question_about_routes(
        self, question: str, routes: list[VehicleRoute], depot: DepotLocation
    ) -> str:
        """Responde perguntas em linguagem natural sobre as rotas otimizadas."""
        routes_summary = "\n".join(
            f"{route.vehicle.label}: {len(route.deliveries)} entregas, "
            f"{route.total_weight_kg:.1f}kg / {route.vehicle.capacity_kg:.1f}kg capacidade, "
            f"{route.distance_km(depot.coordinates):.1f}km / {route.vehicle.max_range_km:.1f}km autonomia, "
            f"criticos: {sum(1 for d in route.deliveries if d.is_critical)}"
            for route in routes
        )
        system_prompt = (
            "Voce e um assistente que responde perguntas sobre rotas de entrega "
            "de medicamentos com base nos dados fornecidos. Seja direto e preciso. "
            "Responda em portugues do Brasil."
        )
        user_prompt = (
            f"Dados das rotas otimizadas:\n{routes_summary}\n\n"
            f"Pergunta do usuario: {question}"
        )
        return self._send_prompt(system_prompt, user_prompt)
