"""
Algoritmo Genetico principal para o problema de roteamento de veiculos (VRP)
do MedRoutes. Implementado do zero, sem bibliotecas de AG (ex.: DEAP).

Fluxo geral:
    1. Inicializa uma populacao de cromossomos aleatorios (permutacoes).
    2. A cada geracao: avalia fitness, seleciona pais por torneio, aplica
       crossover OX e mutacao por inversao, e monta a proxima geracao.
    3. Aplica elitismo: o(s) melhor(es) individuo(s) da geracao atual
       sempre sobrevivem para a proxima, garantindo que o fitness nunca
       piore entre geracoes.
    4. Retorna a melhor solucao encontrada e o historico de fitness.
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
    """Hiperparametros configuraveis do AG.

    Attributes:
        population_size: Numero de individuos por geracao.
        num_generations: Numero de geracoes a evoluir.
        mutation_rate: Probabilidade de mutacao por inversao em cada filho.
        tournament_size: Tamanho do torneio na selecao de pais.
        elitism_count: Quantidade de melhores individuos preservados por geracao.
        random_seed: Semente do gerador aleatorio, para reprodutibilidade.
        fitness_weights: Pesos usados na funcao fitness.
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
    """Estatisticas de fitness coletadas em uma geracao (para analise/plots)."""

    generation: int
    best_fitness: float
    average_fitness: float
    worst_fitness: float


@dataclass
class GeneticAlgorithmResult:
    """Resultado final da execucao do AG.

    Attributes:
        best_chromosome: Melhor permutacao encontrada.
        best_fitness: Fitness do melhor cromossomo (menor = melhor).
        best_routes: Rotas decodificadas por veiculo, ja otimizadas.
        history: Estatisticas de fitness por geracao (para graficos).
        elapsed_seconds: Tempo total de execucao do AG.
        config: Configuracao usada nesta execucao (util para comparativos).
    """

    best_chromosome: Chromosome
    best_fitness: float
    best_routes: list[VehicleRoute]
    history: list[GenerationStats]
    elapsed_seconds: float
    config: GeneticAlgorithmConfig


class GeneticAlgorithm:
    """Algoritmo Genetico para otimizacao de rotas de entrega (VRP)."""

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
        # elitismo: preserva os N melhores individuos sem alteracao
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
        """Executa o AG completo e retorna a melhor solucao encontrada."""
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
