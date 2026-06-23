"""Testes da funcao fitness e decodificacao de cromossomos."""

from __future__ import annotations

import pytest

from app.genetic.fitness import (
    FitnessWeights,
    decode_chromosome,
    evaluate_fitness,
    haversine_distance_km,
)


def test_haversine_distance_zero_for_same_point():
    coord = (-23.5505, -46.6333)
    assert haversine_distance_km(coord, coord) == pytest.approx(0.0, abs=1e-9)


def test_haversine_distance_known_points():
    # Sao Paulo -> Rio de Janeiro (aprox. 360km em linha reta)
    sao_paulo = (-23.5505, -46.6333)
    rio_de_janeiro = (-22.9068, -43.1729)
    distance = haversine_distance_km(sao_paulo, rio_de_janeiro)
    assert 340 < distance < 380


def test_decode_chromosome_respects_capacity_when_possible(sample_problem):
    chromosome = [0, 1, 2, 3]
    routes = decode_chromosome(chromosome, sample_problem)

    assert sum(len(r.deliveries) for r in routes) == 4
    for route in routes:
        assert route.is_within_capacity()


def test_decode_chromosome_distributes_across_vehicles(sample_problem):
    # pesos somam 26kg, capacidade de cada veiculo e 15kg -> precisa dos 2
    chromosome = [0, 1, 2, 3]
    routes = decode_chromosome(chromosome, sample_problem)
    non_empty_routes = [r for r in routes if r.deliveries]
    assert len(non_empty_routes) >= 2


def test_evaluate_fitness_is_non_negative(sample_problem):
    chromosome = [0, 1, 2, 3]
    fitness = evaluate_fitness(chromosome, sample_problem)
    assert fitness >= 0.0


def test_evaluate_fitness_penalizes_capacity_violation(sample_problem):
    # forca todas as entregas em um cenario com 1 veiculo so, violando capacidade
    sample_problem.vehicles = sample_problem.vehicles[:1]
    sample_problem.vehicles[0].capacity_kg = 5.0  # menor que o total de 26kg

    chromosome = [0, 1, 2, 3]
    weights = FitnessWeights(capacity_penalty=1000.0)
    fitness = evaluate_fitness(chromosome, sample_problem, weights)

    # com penalidade alta, o fitness deve ser dominado pela violacao de capacidade
    assert fitness > 1000.0


def test_evaluate_fitness_rewards_critical_deliveries_first(sample_problem):
    """Uma rota que entrega o item critico primeiro deve ter fitness menor
    do que a mesma rota com o item critico entregue por ultimo."""
    weights = FitnessWeights(distance_weight=0.0, priority_weight=5.0)

    # d1 (critico) primeiro, d2 (regular) depois
    chromosome_critical_first = [0, 1]
    # d2 (regular) primeiro, d1 (critico) depois
    chromosome_critical_last = [1, 0]

    sample_problem.vehicles = sample_problem.vehicles[:1]
    sample_problem.vehicles[0].capacity_kg = 100.0

    fitness_critical_first = evaluate_fitness(chromosome_critical_first, sample_problem, weights)
    fitness_critical_last = evaluate_fitness(chromosome_critical_last, sample_problem, weights)

    assert fitness_critical_first < fitness_critical_last
