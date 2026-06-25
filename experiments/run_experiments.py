"""
Script de experimentos comparativos do Algoritmo Genético.

Roda o AG com 4 configurações diferentes (variando tamanho de população,
taxa de mutação e pressão seletiva) sobre o mesmo cenário sintético de
entregas. Para dar rigor estatístico, CADA configuração é executada com
múltiplas sementes (N seeds) e os resultados são reportados como
média ± desvio-padrão — em vez de uma única execução, que seria sensível
à sorte de uma semente específica.

Além disso, compara o AG com dois baselines de referência:
    - rota aleatória (piso trivial);
    - heurística do vizinho-mais-próximo (nearest neighbor).

Uso:
    python experiments/run_experiments.py

Saída:
    - experiments/results/comparison.csv      (tabela agregada média ± dp)
    - experiments/results/convergence.json    (curvas médias de convergência
      por configuração + baselines, consumidas pelo gerador de gráfico)
    - impressão no console da tabela comparativa
"""

from __future__ import annotations

import csv
import json
import os
import random
import statistics
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.genetic.algorithm import GeneticAlgorithm, GeneticAlgorithmConfig
from app.genetic.fitness import (
    FitnessWeights,
    decode_chromosome,
    haversine_distance_km,
)
from app.genetic.operators import create_random_chromosome
from app.models.delivery import Delivery, DeliveryType, DepotLocation, RoutingProblem, Vehicle

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# sementes usadas para repetir cada configuração e medir variabilidade
SEEDS = list(range(10))
NUM_GENERATIONS = 120


def build_synthetic_problem(num_deliveries: int = 25, num_vehicles: int = 4, seed: int = 7) -> RoutingProblem:
    """Cria um cenário sintético de entregas em torno de um depósito fixo.

    Usado para os experimentos comparativos sem depender de chamadas reais
    de geocodificação (Nominatim), mantendo os experimentos reproduzíveis
    e offline. A semente do CENÁRIO (seed=7) é independente da semente do
    AG (random_seed), que é variada nos experimentos.
    """
    rng = random.Random(seed)
    depot = DepotLocation(address="Depósito Central", latitude=-23.5505, longitude=-46.6333)

    deliveries: list[Delivery] = []
    for i in range(num_deliveries):
        delivery_type = (
            DeliveryType.CRITICAL_MEDICATION if i % 3 == 0 else DeliveryType.REGULAR_SUPPLY
        )
        deliveries.append(
            Delivery(
                id=f"d{i}",
                address=f"Endereço sintético {i}",
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


# --------------------------------------------------------------------------- #
# Baselines de referência (para comparar com o AG)
# --------------------------------------------------------------------------- #
def random_baseline_distance(problem: RoutingProblem, seeds: list[int]) -> float:
    """Distância média de rotas puramente aleatórias (piso trivial)."""
    distances = []
    depot_coords = problem.depot.coordinates
    for seed in seeds:
        rng = random.Random(seed)
        chromosome = create_random_chromosome(len(problem.deliveries), rng=rng)
        routes = decode_chromosome(chromosome, problem)
        distances.append(sum(r.distance_km(depot_coords) for r in routes))
    return statistics.mean(distances)


def nearest_neighbor_distance(problem: RoutingProblem) -> float:
    """Distância de uma rota construída pela heurística do vizinho-mais-próximo.

    A partir do depósito, escolhe repetidamente a entrega não visitada mais
    próxima da posição atual. A ordem resultante é decodificada pela mesma
    função do AG (`decode_chromosome`), garantindo uma comparação justa.
    """
    depot_coords = problem.depot.coordinates
    remaining = list(range(len(problem.deliveries)))
    order: list[int] = []
    current = depot_coords

    while remaining:
        nxt = min(
            remaining,
            key=lambda i: haversine_distance_km(current, problem.deliveries[i].coordinates),
        )
        order.append(nxt)
        current = problem.deliveries[nxt].coordinates
        remaining.remove(nxt)

    routes = decode_chromosome(order, problem)
    return sum(r.distance_km(depot_coords) for r in routes)


# --------------------------------------------------------------------------- #
# Experimentos do AG (multi-seed)
# --------------------------------------------------------------------------- #
@dataclass
class AggregatedResult:
    name: str
    population_size: int
    mutation_rate: float
    tournament_size: int
    num_generations: int
    num_seeds: int
    fitness_mean: float
    fitness_std: float
    distance_mean: float
    distance_std: float
    elapsed_mean: float
    best_generation_mean: float


def _make_config(population_size: int, mutation_rate: float, tournament_size: int,
                 elitism_count: int, seed: int) -> GeneticAlgorithmConfig:
    return GeneticAlgorithmConfig(
        population_size=population_size,
        num_generations=NUM_GENERATIONS,
        mutation_rate=mutation_rate,
        tournament_size=tournament_size,
        elitism_count=elitism_count,
        random_seed=seed,
        fitness_weights=FitnessWeights(),
    )


# (nome, population_size, mutation_rate, tournament_size, elitism_count)
EXPERIMENT_CONFIGS: list[tuple[str, int, float, int, int]] = [
    ("Config A - população pequena, mutação baixa", 30, 0.05, 3, 2),
    ("Config B - população grande, mutação baixa", 150, 0.05, 3, 4),
    ("Config C - população média, mutação alta", 80, 0.40, 3, 2),
    ("Config D - população média, mutação baixa, torneio maior", 80, 0.10, 6, 2),
]


def run_config_over_seeds(
    name: str, pop: int, mut: float, tournament: int, elitism: int, problem: RoutingProblem
) -> tuple[AggregatedResult, list[float]]:
    """Executa uma configuração para todas as sementes e agrega os resultados.

    Retorna o resultado agregado (média ± dp) e a curva MÉDIA de convergência
    (best_fitness por geração, média entre as sementes).
    """
    depot_coords = problem.depot.coordinates
    fitnesses: list[float] = []
    distances: list[float] = []
    elapsed_list: list[float] = []
    best_generations: list[int] = []
    curves: list[list[float]] = []

    for seed in SEEDS:
        config = _make_config(pop, mut, tournament, elitism, seed)
        result = GeneticAlgorithm(problem, config).run()

        fitnesses.append(result.best_fitness)
        distances.append(sum(r.distance_km(depot_coords) for r in result.best_routes))
        elapsed_list.append(result.elapsed_seconds)
        best_generations.append(
            min(range(len(result.history)), key=lambda i: result.history[i].best_fitness)
        )
        curves.append([stats.best_fitness for stats in result.history])

    # curva média de convergência: média elemento a elemento entre as sementes
    mean_curve = [statistics.mean(gen_values) for gen_values in zip(*curves)]

    aggregated = AggregatedResult(
        name=name,
        population_size=pop,
        mutation_rate=mut,
        tournament_size=tournament,
        num_generations=NUM_GENERATIONS,
        num_seeds=len(SEEDS),
        fitness_mean=round(statistics.mean(fitnesses), 3),
        fitness_std=round(statistics.stdev(fitnesses), 3) if len(fitnesses) > 1 else 0.0,
        distance_mean=round(statistics.mean(distances), 2),
        distance_std=round(statistics.stdev(distances), 2) if len(distances) > 1 else 0.0,
        elapsed_mean=round(statistics.mean(elapsed_list), 3),
        best_generation_mean=round(statistics.mean(best_generations), 1),
    )
    return aggregated, mean_curve


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    problem = build_synthetic_problem()

    # baselines de referência
    baseline_random = random_baseline_distance(problem, SEEDS)
    baseline_nn = nearest_neighbor_distance(problem)

    results: list[AggregatedResult] = []
    convergence_curves: dict[str, list[float]] = {}

    for name, pop, mut, tournament, elitism in EXPERIMENT_CONFIGS:
        print(f"Executando ({len(SEEDS)} sementes): {name}...")
        aggregated, curve = run_config_over_seeds(name, pop, mut, tournament, elitism, problem)
        results.append(aggregated)
        convergence_curves[name] = curve

    # CSV agregado
    csv_path = os.path.join(RESULTS_DIR, "comparison.csv")
    fieldnames = [
        "name", "population_size", "mutation_rate", "tournament_size",
        "num_generations", "num_seeds", "fitness_mean", "fitness_std",
        "distance_mean", "distance_std", "elapsed_mean", "best_generation_mean",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r.__dict__)

    # JSON de convergência (consumido pelo gerador de gráfico)
    convergence_path = os.path.join(RESULTS_DIR, "convergence.json")
    with open(convergence_path, "w", encoding="utf-8") as json_file:
        json.dump(
            {
                "scenario": {
                    "num_deliveries": len(problem.deliveries),
                    "num_vehicles": len(problem.vehicles),
                    "num_seeds": len(SEEDS),
                    "num_generations": NUM_GENERATIONS,
                },
                "baselines": {
                    "aleatorio_km": round(baseline_random, 2),
                    "vizinho_mais_proximo_km": round(baseline_nn, 2),
                },
                "configs": {
                    r.name: {
                        "population_size": r.population_size,
                        "mutation_rate": r.mutation_rate,
                        "curve": convergence_curves[r.name],
                    }
                    for r in results
                },
            },
            json_file,
            ensure_ascii=False,
            indent=2,
        )

    # impressão no console
    print("\n=== Baselines de distância (cenário fixo) ===")
    print(f"Rota aleatória (média de {len(SEEDS)} sementes): {baseline_random:.2f} km")
    print(f"Vizinho-mais-próximo (heurística determinística): {baseline_nn:.2f} km")

    print("\n=== Tabela comparativa (média ± desvio-padrão entre sementes) ===")
    header = f"{'Configuração':52} {'Pop':>4} {'Mut':>5} {'Fitness (média±dp)':>22} {'Dist.km (média±dp)':>22} {'Tempo(s)':>9}"
    print(header)
    print("-" * len(header))
    for r in results:
        fitness_col = f"{r.fitness_mean:.1f} ± {r.fitness_std:.1f}"
        dist_col = f"{r.distance_mean:.1f} ± {r.distance_std:.1f}"
        print(
            f"{r.name:52} {r.population_size:>4} {r.mutation_rate:>5.2f} "
            f"{fitness_col:>22} {dist_col:>22} {r.elapsed_mean:>9.3f}"
        )

    best_overall = min(results, key=lambda r: r.fitness_mean)
    print(f"\nMelhor configuração (menor fitness médio): {best_overall.name} "
          f"(fitness={best_overall.fitness_mean:.1f} ± {best_overall.fitness_std:.1f})")
    print(f"\nResultados salvos em:\n  {csv_path}\n  {convergence_path}")


if __name__ == "__main__":
    main()
