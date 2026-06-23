"""
Script de experimentos comparativos do Algoritmo Genetico.

Roda o AG com pelo menos 3 configuracoes diferentes (variando tamanho de
populacao e taxa de mutacao) sobre o mesmo cenario sintetico de entregas,
e gera uma tabela comparativa de performance (fitness final, distancia
total, tempo de execucao, geracao em que o melhor fitness foi atingido).

Uso:
    python experiments/run_experiments.py

Saida:
    - experiments/results/comparison.csv
    - experiments/results/convergence.png (grafico de convergencia por config)
    - impressao no console da tabela comparativa
"""

from __future__ import annotations

import csv
import os
import random
import sys
from dataclasses import asdict, dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.genetic.algorithm import GeneticAlgorithm, GeneticAlgorithmConfig
from app.genetic.fitness import FitnessWeights
from app.models.delivery import Delivery, DeliveryType, DepotLocation, RoutingProblem, Vehicle

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def build_synthetic_problem(num_deliveries: int = 25, num_vehicles: int = 4, seed: int = 7) -> RoutingProblem:
    """Cria um cenario sintetico de entregas em torno de um deposito fixo.

    Usado para os experimentos comparativos sem depender de chamadas reais
    de geocodificacao (Nominatim), mantendo os experimentos reprodutiveis
    e offline.
    """
    rng = random.Random(seed)
    depot = DepotLocation(address="Deposito Central", latitude=-23.5505, longitude=-46.6333)

    deliveries: list[Delivery] = []
    for i in range(num_deliveries):
        delivery_type = (
            DeliveryType.CRITICAL_MEDICATION if i % 3 == 0 else DeliveryType.REGULAR_SUPPLY
        )
        deliveries.append(
            Delivery(
                id=f"d{i}",
                address=f"Endereco sintetico {i}",
                delivery_type=delivery_type,
                weight_kg=rng.uniform(1.0, 12.0),
                latitude=-23.5505 + rng.uniform(-0.15, 0.15),
                longitude=-46.6333 + rng.uniform(-0.15, 0.15),
            )
        )

    vehicles = [
        Vehicle(id=f"v{i}", capacity_kg=40.0, max_range_km=80.0) for i in range(num_vehicles)
    ]

    return RoutingProblem(deliveries=deliveries, vehicles=vehicles, depot=depot)


@dataclass
class ExperimentResult:
    name: str
    population_size: int
    mutation_rate: float
    tournament_size: int
    num_generations: int
    best_fitness: float
    total_distance_km: float
    elapsed_seconds: float
    best_generation: int


def compute_total_distance(result, depot_coords) -> float:
    return sum(route.distance_km(depot_coords) for route in result.best_routes)


def run_single_experiment(name: str, problem: RoutingProblem, config: GeneticAlgorithmConfig) -> tuple[ExperimentResult, list[float]]:
    ga = GeneticAlgorithm(problem, config)
    result = ga.run()

    best_generation = min(range(len(result.history)), key=lambda i: result.history[i].best_fitness)
    total_distance = compute_total_distance(result, problem.depot.coordinates)

    experiment_result = ExperimentResult(
        name=name,
        population_size=config.population_size,
        mutation_rate=config.mutation_rate,
        tournament_size=config.tournament_size,
        num_generations=config.num_generations,
        best_fitness=round(result.best_fitness, 3),
        total_distance_km=round(total_distance, 2),
        elapsed_seconds=round(result.elapsed_seconds, 3),
        best_generation=best_generation,
    )
    convergence_curve = [stats.best_fitness for stats in result.history]
    return experiment_result, convergence_curve


EXPERIMENT_CONFIGS: list[tuple[str, GeneticAlgorithmConfig]] = [
    (
        "Config A - populacao pequena, mutacao baixa",
        GeneticAlgorithmConfig(
            population_size=30, num_generations=120, mutation_rate=0.05,
            tournament_size=3, elitism_count=2, random_seed=42,
            fitness_weights=FitnessWeights(),
        ),
    ),
    (
        "Config B - populacao grande, mutacao baixa",
        GeneticAlgorithmConfig(
            population_size=150, num_generations=120, mutation_rate=0.05,
            tournament_size=3, elitism_count=4, random_seed=42,
            fitness_weights=FitnessWeights(),
        ),
    ),
    (
        "Config C - populacao media, mutacao alta",
        GeneticAlgorithmConfig(
            population_size=80, num_generations=120, mutation_rate=0.40,
            tournament_size=3, elitism_count=2, random_seed=42,
            fitness_weights=FitnessWeights(),
        ),
    ),
    (
        "Config D - populacao media, mutacao baixa, torneio maior",
        GeneticAlgorithmConfig(
            population_size=80, num_generations=120, mutation_rate=0.10,
            tournament_size=6, elitism_count=2, random_seed=42,
            fitness_weights=FitnessWeights(),
        ),
    ),
]


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    problem = build_synthetic_problem()

    results: list[ExperimentResult] = []
    convergence_curves: dict[str, list[float]] = {}

    for name, config in EXPERIMENT_CONFIGS:
        print(f"Executando: {name}...")
        experiment_result, curve = run_single_experiment(name, problem, config)
        results.append(experiment_result)
        convergence_curves[name] = curve

    csv_path = os.path.join(RESULTS_DIR, "comparison.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))

    print("\n=== Tabela comparativa ===")
    header = f"{'Configuracao':45} {'Pop':>5} {'Mut':>6} {'Fitness':>10} {'Dist(km)':>10} {'Tempo(s)':>9} {'Gen.melhor':>11}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.name:45} {r.population_size:>5} {r.mutation_rate:>6.2f} "
            f"{r.best_fitness:>10.2f} {r.total_distance_km:>10.2f} "
            f"{r.elapsed_seconds:>9.3f} {r.best_generation:>11}"
        )

    best_overall = min(results, key=lambda r: r.best_fitness)
    print(f"\nMelhor configuracao: {best_overall.name} (fitness={best_overall.best_fitness})")
    print(f"Resultados salvos em: {csv_path}")

    _plot_convergence(convergence_curves)


def _plot_convergence(convergence_curves: dict[str, list[float]]) -> None:
    """Gera grafico de convergencia comparando as configuracoes. Sem falhar
    o script caso matplotlib nao esteja disponivel."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib nao instalado: grafico de convergencia nao gerado.")
        return

    plt.figure(figsize=(10, 6))
    for name, curve in convergence_curves.items():
        plt.plot(curve, label=name)
    plt.xlabel("Geracao")
    plt.ylabel("Melhor fitness (menor = melhor)")
    plt.title("Convergencia do Algoritmo Genetico por configuracao")
    plt.legend(fontsize=8)
    plt.tight_layout()

    plot_path = os.path.join(RESULTS_DIR, "convergence.png")
    plt.savefig(plot_path, dpi=150)
    print(f"Grafico de convergencia salvo em: {plot_path}")


if __name__ == "__main__":
    main()
