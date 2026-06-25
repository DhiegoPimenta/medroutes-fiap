"""
Integração com a API da Anthropic (Claude) para gerar conteúdo em
linguagem natural a partir das rotas otimizadas pelo Algoritmo Genético.

Funcionalidades:
    - Instruções detalhadas de entrega para cada motorista.
    - Relatório de eficiência da rota (distância, tempo estimado, economia
      em relação a uma rota aleatória/não otimizada).
    - Respostas a perguntas em linguagem natural sobre as rotas.

A ANTHROPIC_API_KEY é lida exclusivamente de variável de ambiente (nunca
hardcoded), seguindo a restrição de segurança do projeto.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.genetic.fitness import VehicleRoute
from app.models.delivery import DepotLocation

DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeClientError(Exception):
    """Lançado quando a chamada à API da Anthropic falha ou a chave não existe."""


@dataclass
class RouteEfficiencyMetrics:
    """Métricas resumidas usadas para compor prompts de relatório/instruções."""

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
                "ANTHROPIC_API_KEY não configurada. Defina a variável de "
                "ambiente antes de usar funcionalidades de IA generativa."
            )

        try:
            import anthropic
        except ImportError as error:
            raise ClaudeClientError(
                "Biblioteca 'anthropic' não instalada. Rode `poetry install`."
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
        except Exception as error:  # erro genérico do SDK da Anthropic
            raise ClaudeClientError(f"Falha ao chamar a API da Anthropic: {error}") from error

        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )

    def generate_driver_instructions(
        self, route: VehicleRoute, depot: DepotLocation
    ) -> str:
        """Gera instruções detalhadas em linguagem natural para um motorista."""
        stops_description = "\n".join(
            f"{i+1}. {d.label} - {d.weight_kg:.1f}kg - "
            f"{'MEDICAMENTO CRÍTICO' if d.is_critical else 'Insumo regular'}"
            for i, d in enumerate(route.deliveries)
        )
        system_prompt = (
            "Você é um assistente de logística que escreve instruções claras, "
            "objetivas e amigáveis para motoristas de entrega de medicamentos "
            "e insumos hospitalares. Responda em português do Brasil."
        )
        user_prompt = (
            f"Gere instruções de entrega para o motorista do {route.vehicle.label}.\n"
            f"Ponto de partida: {depot.address}.\n"
            f"Paradas na ordem definida (NÃO reordene):\n{stops_description}\n\n"
            "Inclua: ordem das paradas, atenção especial para itens críticos "
            "(entregar com prioridade e cuidado), e um lembrete de retornar ao depósito."
        )
        return self._send_prompt(system_prompt, user_prompt)

    def generate_efficiency_report(self, metrics: RouteEfficiencyMetrics) -> str:
        """Gera relatório de eficiência comparando a rota otimizada a uma rota aleatória."""
        system_prompt = (
            "Você é um analista de logística que resume métricas de eficiência "
            "de roteamento de forma clara para gestores não técnicos. "
            "Responda em português do Brasil."
        )
        user_prompt = (
            "Resuma a eficiência da rota otimizada com base nestas métricas:\n"
            f"- Distância total otimizada: {metrics.total_distance_km:.1f} km\n"
            f"- Distância de uma rota aleatória (baseline): {metrics.random_baseline_distance_km:.1f} km\n"
            f"- Economia: {metrics.distance_savings_km:.1f} km ({metrics.distance_savings_percent:.1f}%)\n"
            f"- Veículos utilizados: {metrics.num_vehicles_used}\n"
            f"- Total de entregas: {metrics.num_deliveries} (sendo {metrics.num_critical_deliveries} críticas)\n"
            f"- Tempo estimado de execução: {metrics.estimated_time_hours:.1f} horas\n\n"
            "Escreva um parágrafo executivo destacando o ganho de eficiência "
            "e a importância de priorizar as entregas críticas."
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
            f"críticos: {sum(1 for d in route.deliveries if d.is_critical)}"
            for route in routes
        )
        system_prompt = (
            "Você é um assistente que responde perguntas sobre rotas de entrega "
            "de medicamentos com base nos dados fornecidos. Seja direto e preciso. "
            "Responda em português do Brasil."
        )
        user_prompt = (
            f"Dados das rotas otimizadas:\n{routes_summary}\n\n"
            f"Pergunta do usuário: {question}"
        )
        return self._send_prompt(system_prompt, user_prompt)
