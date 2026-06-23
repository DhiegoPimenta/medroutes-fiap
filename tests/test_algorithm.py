"""Testes de integracao do loop principal do Algoritmo Genetico."""

from __future__ import annotations

from app.genetic.algorithm import GeneticAlgorithm, GeneticAlgorithmConfig
from app.genetic.fitness import evaluate_fitness


def test_algorithm_runs_and_returns_result(sample_problem):
    config = GeneticAlgorithmConfig(population_size=20, num_generations=15, random_seed=42)
    ga = GeneticAlgorithm(sample_problem, config)
    result = ga.run()

    assert sorted(result.best_chromosome) == list(range(len(sample_problem.deliveries)))
    assert result.best_fitness >= 0.0
    assert len(result.history) == config.num_generations
    assert result.elapsed_seconds >= 0.0


def test_algorithm_fitness_does_not_worsen_across_generations_with_elitism(sample_problem):
    """Com elitismo, o melhor fitness historico deve ser monotono nao-crescente."""
    config = GeneticAlgorithmConfig(population_size=20, num_generations=20, random_seed=1, elitism_count=2)
    ga = GeneticAlgorithm(sample_problem, config)
    result = ga.run()

    best_so_far = float("inf")
    for stats in result.history:
        assert stats.best_fitness <= best_so_far + 1e-9
        best_so_far = min(best_so_far, stats.best_fitness)


def test_algorithm_best_chromosome_matches_reported_fitness(sample_problem):
    config = GeneticAlgorithmConfig(population_size=15, num_generations=10, random_seed=99)
    ga = GeneticAlgorithm(sample_problem, config)
    result = ga.run()

    recomputed_fitness = evaluate_fitness(result.best_chromosome, sample_problem, config.fitness_weights)
    assert recomputed_fitness == result.best_fitness


def test_algorithm_raises_when_problem_invalid(sample_deliveries, sample_vehicles):
    from app.models.delivery import RoutingProblem

    invalid_problem = RoutingProblem(deliveries=sample_deliveries, vehicles=sample_vehicles, depot=None)
    try:
        GeneticAlgorithm(invalid_problem)
        assert False, "deveria ter lancado ValueError por deposito ausente"
    except ValueError:
        pass
