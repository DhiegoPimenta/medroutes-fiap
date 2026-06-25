"""
Modelos de dados do domínio MedRoutes.

Define as entidades principais do problema de roteamento de veículos (VRP):
entregas (medicamentos críticos ou insumos regulares) e veículos disponíveis
para realizar as entregas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DeliveryType(str, Enum):
    """Tipo de entrega: define a prioridade no roteamento."""

    CRITICAL_MEDICATION = "medicamento_critico"
    REGULAR_SUPPLY = "insumo_regular"

    @property
    def priority_weight(self) -> float:
        """Peso de prioridade usado na função fitness do AG.

        Medicamentos críticos recebem peso maior, fazendo o AG preferir
        rotas que entreguem esses itens mais cedo (menor índice na rota).
        """
        if self is DeliveryType.CRITICAL_MEDICATION:
            return 3.0
        return 1.0


@dataclass
class Delivery:
    """Representa uma entrega individual a ser roteada.

    Attributes:
        id: Identificador único da entrega.
        address: Endereço textual informado pelo usuário.
        delivery_type: Tipo da entrega (crítico ou regular).
        weight_kg: Peso/volume da carga em quilogramas.
        latitude: Latitude geocodificada (preenchida após geocoding).
        longitude: Longitude geocodificada (preenchida após geocoding).
        label: Rótulo amigável exibido na interface e no mapa.
    """

    id: str
    address: str
    delivery_type: DeliveryType
    weight_kg: float
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    label: Optional[str] = None

    def __post_init__(self) -> None:
        if self.weight_kg <= 0:
            raise ValueError("weight_kg deve ser maior que zero")
        if not self.label:
            self.label = self.address

    @property
    def is_geocoded(self) -> bool:
        """Indica se o endereço já possui coordenadas válidas."""
        return self.latitude is not None and self.longitude is not None

    @property
    def is_critical(self) -> bool:
        """Indica se a entrega é de medicamento crítico."""
        return self.delivery_type is DeliveryType.CRITICAL_MEDICATION

    @property
    def coordinates(self) -> tuple[float, float]:
        """Retorna a tupla (lat, lon). Lança erro se não geocodificado."""
        if not self.is_geocoded:
            raise ValueError(f"Entrega {self.id} ainda não foi geocodificada")
        return (self.latitude, self.longitude)  # type: ignore[return-value]


@dataclass
class Vehicle:
    """Representa um veículo disponível para realizar entregas.

    Attributes:
        id: Identificador único do veículo.
        capacity_kg: Capacidade máxima de carga em quilogramas.
        max_range_km: Autonomia máxima (distância total que pode percorrer).
        label: Rótulo amigável exibido na interface e no mapa.
    """

    id: str
    capacity_kg: float
    max_range_km: float
    label: Optional[str] = None

    def __post_init__(self) -> None:
        if self.capacity_kg <= 0:
            raise ValueError("capacity_kg deve ser maior que zero")
        if self.max_range_km <= 0:
            raise ValueError("max_range_km deve ser maior que zero")
        if not self.label:
            self.label = f"Veículo {self.id}"


@dataclass
class DepotLocation:
    """Representa o ponto de partida/retorno (depósito/centro de distribuição)."""

    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @property
    def is_geocoded(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def coordinates(self) -> tuple[float, float]:
        if not self.is_geocoded:
            raise ValueError("Depósito ainda não foi geocodificado")
        return (self.latitude, self.longitude)  # type: ignore[return-value]


@dataclass
class RoutingProblem:
    """Agrupa todos os dados necessários para o AG resolver o VRP.

    Attributes:
        deliveries: Lista de entregas a serem roteadas.
        vehicles: Lista de veículos disponíveis.
        depot: Ponto de partida e retorno de todas as rotas.
    """

    deliveries: list[Delivery] = field(default_factory=list)
    vehicles: list[Vehicle] = field(default_factory=list)
    depot: Optional[DepotLocation] = None

    def validate(self) -> None:
        """Valida se o problema está pronto para ser otimizado pelo AG."""
        if not self.deliveries:
            raise ValueError("É necessário cadastrar ao menos uma entrega")
        if not self.vehicles:
            raise ValueError("É necessário cadastrar ao menos um veículo")
        if self.depot is None or not self.depot.is_geocoded:
            raise ValueError("O depósito precisa estar definido e geocodificado")
        if not all(d.is_geocoded for d in self.deliveries):
            raise ValueError("Todas as entregas precisam estar geocodificadas")

        total_weight = sum(d.weight_kg for d in self.deliveries)
        total_capacity = sum(v.capacity_kg for v in self.vehicles)
        if total_weight > total_capacity:
            raise ValueError(
                "Peso total das entregas "
                f"({total_weight:.2f} kg) excede a capacidade total da frota "
                f"({total_capacity:.2f} kg)"
            )
