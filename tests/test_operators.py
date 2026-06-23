"""Testes dos operadores geneticos: selecao, crossover OX e mutacao por inversao."""

from __future__ import annotations

import random

from app.genetic.operators import (
    create_random_chromosome,
    inversion_mutation,
    order_crossover,
    tournament_selection,
)


def test_create_random_chromosome_is_valid_permutation():
    chromosome = create_random_chromosome(10, rng=random.Random(1))
    assert sorted(chromosome) == list(range(10))


def test_tournament_selection_returns_individual_from_population():
    population = [[0, 1, 2], [2, 1, 0], [1, 0, 2]]
    fitness_values = [10.0, 5.0, 20.0]
    selected = tournament_selection(population, fitness_values, tournament_size=3, rng=random.Random(1))
    assert selected in population


def test_tournament_selection_prefers_lower_fitness_with_full_population_tournament():
    # com tournament_size == tamanho da populacao, sempre escolhe o melhor individuo
    population = [[0, 1, 2], [2, 1, 0], [1, 0, 2]]
    fitness_values = [10.0, 5.0, 20.0]
    selected = tournament_selection(population, fitness_values, tournament_size=3, rng=random.Random(42))
    assert selected == [2, 1, 0]


def test_order_crossover_produces_valid_permutation():
    rng = random.Random(7)
    parent_a = [0, 1, 2, 3, 4, 5]
    parent_b = [5, 4, 3, 2, 1, 0]

    for _ in range(20):
        child = order_crossover(parent_a, parent_b, rng=rng)
        assert sorted(child) == sorted(parent_a)
        assert len(child) == len(parent_a)


def test_order_crossover_preserves_segment_from_parent_a():
    rng = random.Random(0)
    parent_a = [0, 1, 2, 3, 4]
    parent_b = [4, 3, 2, 1, 0]
    child = order_crossover(parent_a, parent_b, rng=rng)
    # com seed fixa, o segmento copiado de parent_a deve aparecer intacto em child
    assert any(
        child[i : i + 2] == parent_a[i : i + 2] for i in range(len(parent_a) - 1)
    )


def test_inversion_mutation_keeps_same_genes():
    chromosome = [0, 1, 2, 3, 4, 5]
    mutated = inversion_mutation(chromosome, mutation_rate=1.0, rng=random.Random(3))
    assert sorted(mutated) == sorted(chromosome)


def test_inversion_mutation_no_change_when_rate_is_zero():
    chromosome = [0, 1, 2, 3, 4]
    mutated = inversion_mutation(chromosome, mutation_rate=0.0, rng=random.Random(3))
    assert mutated == chromosome


def test_inversion_mutation_changes_order_when_applied():
    chromosome = list(range(20))
    mutated = inversion_mutation(chromosome, mutation_rate=1.0, rng=random.Random(5))
    assert mutated != chromosome
    assert sorted(mutated) == sorted(chromosome)
