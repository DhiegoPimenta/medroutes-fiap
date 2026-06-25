"""
Algoritmo Genético principal para o problema de roteamento de veículos (VRP)
do MedRoutes. Implementado do zero, sem bibliotecas de AG (ex.: DEAP).

Fluxo geral:
    1. Inicializa uma população de cromossomos aleatórios (permutações).
    2. A cada geração: avalia fitness, seleciona pais por torneio, aplica
       crossover OX e mutação por inversão, e monta a próxima geração.
    3. Aplica elitismo: o(s) melhor(es) indivíduo(s) da geração atual
       sempre sobrevivem para a próxima, garantindo que o fitness nunca
       piore entre gerações.
    4. Retorna a melhor solução encontrada e o histórico de fitness.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from app.genetic.fitness import FitnessWeights, VehicleRoute, decode_chromosome, evaluate_fitness
from app.genetic.operators import (
    Chromosome,
    create_random_chromosome,
    inversion_mutation,
    order_crossover,
    tournament_selection,
)
from app.models.delivery import RoutingProblem


@dataclass
class GeneticAlgorithmConfig:
    """Hiperparâmetros configuráveis do AG.

    Attributes:
        population_size: Número de indivíduos por geração.
        num_generations: Número de gerações a evoluir.
        mutation_rate: Probabilidade de mutação por inversão em cada filho.
        tournament_size: Tamanho do torneio na seleção de pais.
        elitism_count: Quantidade de melhores indivíduos preservados por geração.
        random_seed: Semente do gerador aleatório, para reprodutibilidade.
        fitness_weights: Pesos usados na função fitness.
    """

    population_size: int = 80
    num_generations: int = 150
    mutation_rate: float = 0.15
    tournament_size: int = 3
    elitism_count: int = 2
    random_seed: int | None = None
    fitness_weights: FitnessWeights = field(default_factory=FitnessWeights)


@dataclass
class GenerationStats:
    """Estatísticas de fitness coletadas em uma geração (para análise/plots)."""

    generation: int
    best_fitness: float
    average_fitness: float
    worst_fitness: float


@dataclass
class GeneticAlgorithmResult:
    """Resultado final da execução do AG.

    Attributes:
        best_chromosome: Melhor permutação encontrada.
        best_fitness: Fitness do melhor cromossomo (menor = melhor).
        best_routes: Rotas decodificadas por veículo, já otimizadas.
        history: Estatísticas de fitness por geração (para gráficos).
        elapsed_seconds: Tempo total de execução do AG.
        config: Configuração usada nesta execução (útil para comparativos).
    """

    best_chromosome: Chromosome
    best_fitness: float
    best_routes: list[VehicleRoute]
    history: list[GenerationStats]
    elapsed_seconds: float
    config: GeneticAlgorithmConfig


class GeneticAlgorithm:
    """Algoritmo Genético para otimização de rotas de entrega (VRP)."""

    def __init__(self, problem: RoutingProblem, config: GeneticAlgorithmConfig | None = None):
        problem.validate()
        self.problem = problem
        self.config = config or GeneticAlgorithmConfig()
        self.rng = random.Random(self.config.random_seed)
        self._num_genes = len(problem.deliveries)

    def _initialize_population(self) -> list[Chromosome]:
        return [
            create_random_chromosome(self._num_genes, rng=self.rng)
            for _ in range(self.config.population_size)
        ]

    def _evaluate_population(self, population: list[Chromosome]) -> list[float]:
        return [
            evaluate_fitness(chromosome, self.problem, self.config.fitness_weights)
            for chromosome in population
        ]

    def _build_next_generation(
        self, population: list[Chromosome], fitness_values: list[float]
    ) -> list[Chromosome]:
        # elitismo: preserva os N melhores indivíduos sem alteração
        ranked_indices = sorted(range(len(population)), key=lambda i: fitness_values[i])
        next_generation = [
            list(population[i]) for i in ranked_indices[: self.config.elitism_count]
        ]

        while len(next_generation) < self.config.population_size:
            parent_a = tournament_selection(
                population, fitness_values, self.config.tournament_size, self.rng
            )
            parent_b = tournament_selection(
                population, fitness_values, self.config.tournament_size, self.rng
            )
            child = order_crossover(parent_a, parent_b, self.rng)
            child = inversion_mutation(child, self.config.mutation_rate, self.rng)
            next_generation.append(child)

        return next_generation[: self.config.population_size]

    def run(self) -> GeneticAlgorithmResult:
        """Executa o AG completo e retorna a melhor solução encontrada."""
        start_time = time.perf_counter()

        population = self._initialize_population()
        history: list[GenerationStats] = []
        best_chromosome: Chromosome = population[0]
        best_fitness = float("inf")

        for generation in range(self.config.num_generations):
            fitness_values = self._evaluate_population(population)

            gen_best_idx = min(range(len(population)), key=lambda i: fitness_values[i])
            if fitness_values[gen_best_idx] < best_fitness:
                best_fitness = fitness_values[gen_best_idx]
                best_chromosome = list(population[gen_best_idx])

            history.append(
                GenerationStats(
                    generation=generation,
                    best_fitness=fitness_values[gen_best_idx],
                    average_fitness=sum(fitness_values) / len(fitness_values),
                    worst_fitness=max(fitness_values),
                )
            )

            population = self._build_next_generation(population, fitness_values)

        elapsed = time.perf_counter() - start_time
        best_routes = decode_chromosome(best_chromosome, self.problem)

        return GeneticAlgorithmResult(
            best_chromosome=best_chromosome,
            best_fitness=best_fitness,
            best_routes=best_routes,
            history=history,
            elapsed_seconds=elapsed,
            config=self.config,
        )
