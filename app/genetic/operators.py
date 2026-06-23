"""
Operadores geneticos implementados do zero (sem bibliotecas de AG prontas).

Todos os operadores trabalham sobre cromossomos representados como
permutacoes (listas de inteiros, cada inteiro = indice de uma entrega).

Operadores implementados:
    - tournament_selection: selecao por torneio.
    - order_crossover: crossover OX (Order Crossover), adequado para
      permutacoes pois preserva a ordem relativa dos genes sem duplicatas.
    - inversion_mutation: mutacao por inversao de um subtrecho do cromossomo.
"""

from __future__ import annotations

import random
from typing import Callable, Sequence

Chromosome = list[int]


def tournament_selection(
    population: Sequence[Chromosome],
    fitness_values: Sequence[float],
    tournament_size: int = 3,
    rng: random.Random | None = None,
) -> Chromosome:
    """Seleciona um individuo via torneio.

    Sorteia `tournament_size` individuos aleatoriamente da populacao e
    retorna o de menor fitness (problema de minimizacao). Quanto maior o
    `tournament_size`, maior a pressao seletiva (menos diversidade).
    """
    rng = rng or random.Random()
    if tournament_size < 1:
        raise ValueError("tournament_size deve ser >= 1")

    contenders_idx = rng.sample(range(len(population)), k=min(tournament_size, len(population)))
    best_idx = min(contenders_idx, key=lambda i: fitness_values[i])
    return list(population[best_idx])


def order_crossover(
    parent_a: Chromosome,
    parent_b: Chromosome,
    rng: random.Random | None = None,
) -> Chromosome:
    """Crossover OX (Order Crossover) para permutacoes.

    Passos:
    1. Sorteia dois pontos de corte [start, end] em parent_a.
    2. Copia o segmento [start, end] de parent_a diretamente para o filho,
       preservando posicoes.
    3. Preenche as posicoes restantes do filho com os genes de parent_b,
       na ordem em que aparecem em parent_b, pulando os genes que ja
       foram copiados do segmento de parent_a.

    Isso garante que o filho seja uma permutacao valida (sem repeticoes e
    sem omissoes), preservando a ordem relativa herdada de ambos os pais.
    """
    rng = rng or random.Random()
    size = len(parent_a)
    if size != len(parent_b):
        raise ValueError("parent_a e parent_b devem ter o mesmo tamanho")

    start, end = sorted(rng.sample(range(size), 2))

    child: list[int | None] = [None] * size
    segment = parent_a[start : end + 1]
    child[start : end + 1] = segment
    segment_set = set(segment)

    fill_positions = [i for i in range(size) if child[i] is None]
    fill_values = [gene for gene in parent_b if gene not in segment_set]

    for position, value in zip(fill_positions, fill_values):
        child[position] = value

    return child  # type: ignore[return-value]


def inversion_mutation(
    chromosome: Chromosome,
    mutation_rate: float,
    rng: random.Random | None = None,
) -> Chromosome:
    """Mutacao por inversao: com probabilidade `mutation_rate`, inverte um
    subtrecho aleatorio do cromossomo.

    A inversao preserva a validade da permutacao (mesmos genes, ordem
    parcialmente alterada), introduzindo diversidade sem violar restricoes
    estruturais do cromossomo.
    """
    rng = rng or random.Random()
    if not 0.0 <= mutation_rate <= 1.0:
        raise ValueError("mutation_rate deve estar entre 0 e 1")

    mutated = list(chromosome)
    if rng.random() >= mutation_rate:
        return mutated

    size = len(mutated)
    if size < 2:
        return mutated

    start, end = sorted(rng.sample(range(size), 2))
    mutated[start : end + 1] = list(reversed(mutated[start : end + 1]))
    return mutated


def create_random_chromosome(num_genes: int, rng: random.Random | None = None) -> Chromosome:
    """Cria um cromossomo aleatorio: uma permutacao de [0, num_genes)."""
    rng = rng or random.Random()
    genes = list(range(num_genes))
    rng.shuffle(genes)
    return genes
