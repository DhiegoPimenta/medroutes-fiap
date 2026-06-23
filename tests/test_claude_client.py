"""Testes da integracao com a Claude API, sempre com mock (sem chamadas reais)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.llm.claude_client import ClaudeClient, ClaudeClientError, RouteEfficiencyMetrics


def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def test_client_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = ClaudeClient(api_key=None)
    with pytest.raises(ClaudeClientError):
        client._get_client()


def test_generate_driver_instructions_returns_text(sample_problem):
    from app.genetic.fitness import decode_chromosome

    routes = decode_chromosome([0, 1, 2, 3], sample_problem)
    route = next(r for r in routes if r.deliveries)

    client = ClaudeClient(api_key="fake-key")
    mock_anthropic_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [_make_text_block("Instrucoes geradas para o motorista.")]
    mock_anthropic_client.messages.create.return_value = mock_response
    client._client = mock_anthropic_client

    result = client.generate_driver_instructions(route, sample_problem.depot)

    assert "Instrucoes geradas" in result
    mock_anthropic_client.messages.create.assert_called_once()


def test_generate_efficiency_report_returns_text():
    client = ClaudeClient(api_key="fake-key")
    mock_anthropic_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [_make_text_block("Relatorio de eficiencia gerado.")]
    mock_anthropic_client.messages.create.return_value = mock_response
    client._client = mock_anthropic_client

    metrics = RouteEfficiencyMetrics(
        total_distance_km=100.0,
        random_baseline_distance_km=150.0,
        num_vehicles_used=2,
        num_deliveries=10,
        num_critical_deliveries=3,
        estimated_time_hours=4.5,
    )
    result = client.generate_efficiency_report(metrics)

    assert "Relatorio" in result
    assert metrics.distance_savings_km == pytest.approx(50.0)
    assert metrics.distance_savings_percent == pytest.approx(33.333, rel=1e-3)


def test_answer_question_about_routes_returns_text(sample_problem):
    from app.genetic.fitness import decode_chromosome

    routes = decode_chromosome([0, 1, 2, 3], sample_problem)

    client = ClaudeClient(api_key="fake-key")
    mock_anthropic_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [_make_text_block("A entrega d1 e a mais urgente.")]
    mock_anthropic_client.messages.create.return_value = mock_response
    client._client = mock_anthropic_client

    answer = client.answer_question_about_routes(
        "Qual entrega e mais urgente?", routes, sample_problem.depot
    )

    assert "urgente" in answer


def test_send_prompt_wraps_sdk_errors():
    client = ClaudeClient(api_key="fake-key")
    mock_anthropic_client = MagicMock()
    mock_anthropic_client.messages.create.side_effect = RuntimeError("timeout")
    client._client = mock_anthropic_client

    with pytest.raises(ClaudeClientError):
        client._send_prompt("system", "user")
