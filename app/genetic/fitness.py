"""
Funcao fitness e utilitarios de distancia para o Algoritmo Genetico do VRP.

A representacao cromossomica adotada e um "giant tour": uma permutacao com
os indices de TODAS as entregas, sem marcar explicitamente a separacao entre
veiculos. A decodificacao (`decode_chromosome`) percorre essa permutacao e
distribui as entregas entre os veiculos disponiveis respeitando capacidade
de carga e autonomia maxima, abrindo um novo veiculo sempre que o atual nao
comporta a proxima entrega. Essa abordagem permite usar operadores classicos
de permutacao (OX, inversao) mesmo com multiplas rotas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from app.models.delivery import Delivery, RoutingProblem, Vehicle


def haversine_distance_km(
    coord_a: tuple[float, float], coord_b: tuple[float, float]
) -> float:
    """Calcula a distancia em quilometros entre duas coordenadas (lat, lon).

    Usa a formula de Haversine, que considera a curvatura da Terra e e
    adequada para distancias rodoviarias aproximadas em escala urbana.
    """
    lat1, lon1 = coord_a
    lat2, lon2 = coord_b
    radius_earth_km = 6371.0

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_earth_km * c


@dataclass
class VehicleRoute:
    """Rota decodificada de um unico veiculo."""

    vehicle: Vehicle
    deliveries: list[Delivery] = field(default_factory=list)

    @property
    def total_weight_kg(self) -> float:
        return sum(d.weight_kg for d in self.deliveries)

    def distance_km(self, depot_coords: tuple[float, float]) -> float:
        """Distancia total da rota: deposito -> entregas em sequencia -> deposito."""
        if not self.deliveries:
            return 0.0
        total = 0.0
        current = depot_coords
        for delivery in self.deliveries:
            total += haversine_distance_km(current, delivery.coordinates)
            current = delivery.coordinates
        total += haversine_distance_km(current, depot_coords)
        return total

    def is_within_capacity(self) -> bool:
        return self.total_weight_kg <= self.vehicle.capacity_kg

    def is_within_range(self, depot_coords: tuple[float, float]) -> bool:
        return self.distance_km(depot_coords) <= self.vehicle.max_range_km


def decode_chromosome(
    chromosome: Sequence[int], problem: RoutingProblem
) -> list[VehicleRoute]:
    """Decodifica um cromossomo (permutacao de indices de entregas) em rotas.

    Estrategia greedy: percorre a permutacao na ordem dada e tenta encaixar
    cada entrega no veiculo atual. Se a entrega nao couber (capacidade ou
    autonomia excedida), avanca para o proximo veiculo disponivel. Se todos
    os veiculos se esgotarem, as entregas restantes sao acumuladas no ultimo
    veiculo mesmo violando os limites -- a violacao e penalizada fortemente
    na funcao fitness, criando pressao seletiva contra essas solucoes.
    """
    depot_coords = problem.depot.coordinates  # type: ignore[union-attr]
    routes = [VehicleRoute(vehicle=v) for v in problem.vehicles]

    vehicle_index = 0
    for gene in chromosome:
        delivery = problem.deliveries[gene]
        placed = False

        # tenta o veiculo atual e os seguintes, na ordem
        search_index = vehicle_index
        while search_index < len(routes):
            candidate_route = routes[search_index]
            projected_weight = candidate_route.total_weight_kg + delivery.weight_kg
            fits_capacity = projected_weight <= candidate_route.vehicle.capacity_kg

            if fits_capacity:
                candidate_route.deliveries.append(delivery)
                vehicle_index = search_index
                placed = True
                break
            search_index += 1

        if not placed:
            # nenhum veiculo restante comporta a entrega: forca no ultimo
            # veiculo, violando capacidade (penalizado no fitness)
            routes[-1].deliveries.append(delivery)

    return routes


@dataclass
class FitnessWeights:
    """Pesos configuraveis da funcao fitness, usados nos experimentos.

    Attributes:
        distance_weight: Peso da distancia total percorrida pela frota.
        priority_weight: Peso do termo de priorizacao de entregas criticas.
        capacity_penalty: Penalidade por kg excedente de capacidade.
        range_penalty: Penalidade por km excedente de autonomia.
    """

    distance_weight: float = 1.0
    priority_weight: float = 5.0
    capacity_penalty: float = 1000.0
    range_penalty: float = 1000.0


def evaluate_fitness(
    chromosome: Sequence[int],
    problem: RoutingProblem,
    weights: FitnessWeights | None = None,
) -> float:
    """Calcula o fitness de um cromossomo. Quanto MENOR, melhor a solucao.

    O fitness combina quatro componentes:
    1. Distancia total percorrida por toda a frota (minimizar custo/tempo).
    2. Penalizacao de prioridade: entregas criticas posicionadas tarde em
       sua rota aumentam o fitness (queremos que sejam entregues primeiro).
    3. Penalidade de capacidade: kg excedentes acima da capacidade do veiculo.
    4. Penalidade de autonomia: km excedentes acima do alcance maximo.
    """
    weights = weights or FitnessWeights()
    depot_coords = problem.depot.coordinates  # type: ignore[union-attr]
    routes = decode_chromosome(chromosome, problem)

    total_distance = 0.0
    priority_penalty = 0.0
    capacity_penalty_total = 0.0
    range_penalty_total = 0.0

    for route in routes:
        if not route.deliveries:
            continue

        route_distance = route.distance_km(depot_coords)
        total_distance += route_distance

        # penaliza entregas criticas que aparecem tarde na rota: posicao
        # normalizada (0 = primeira entrega, 1 = ultima) multiplicada pelo
        # peso de prioridade do tipo de entrega
        route_length = len(route.deliveries)
        for position, delivery in enumerate(route.deliveries):
            normalized_position = position / max(route_length - 1, 1)
            priority_penalty += (
                normalized_position * delivery.delivery_type.priority_weight
            )

        excess_weight = max(0.0, route.total_weight_kg - route.vehicle.capacity_kg)
        capacity_penalty_total += excess_weight

        excess_range = max(0.0, route_distance - route.vehicle.max_range_km)
        range_penalty_total += excess_range

    fitness = (
        weights.distance_weight * total_distance
        + weights.priority_weight * priority_penalty
        + weights.capacity_penalty * capacity_penalty_total
        + weights.range_penalty * range_penalty_total
    )
    return fitness
