"""Fixtures compartilhadas pelos testes do MedRoutes."""

from __future__ import annotations

import pytest

from app.models.delivery import Delivery, DeliveryType, DepotLocation, RoutingProblem, Vehicle


@pytest.fixture
def sample_depot() -> DepotLocation:
    return DepotLocation(
        address="Deposito Central, Sao Paulo",
        latitude=-23.5505,
        longitude=-46.6333,
    )


@pytest.fixture
def sample_deliveries() -> list[Delivery]:
    return [
        Delivery(
            id="d1",
            address="Rua A, 100",
            delivery_type=DeliveryType.CRITICAL_MEDICATION,
            weight_kg=5.0,
            latitude=-23.5500,
            longitude=-46.6300,
        ),
        Delivery(
            id="d2",
            address="Rua B, 200",
            delivery_type=DeliveryType.REGULAR_SUPPLY,
            weight_kg=10.0,
            latitude=-23.5600,
            longitude=-46.6400,
        ),
        Delivery(
            id="d3",
            address="Rua C, 300",
            delivery_type=DeliveryType.CRITICAL_MEDICATION,
            weight_kg=3.0,
            latitude=-23.5400,
            longitude=-46.6200,
        ),
        Delivery(
            id="d4",
            address="Rua D, 400",
            delivery_type=DeliveryType.REGULAR_SUPPLY,
            weight_kg=8.0,
            latitude=-23.5700,
            longitude=-46.6500,
        ),
    ]


@pytest.fixture
def sample_vehicles() -> list[Vehicle]:
    return [
        Vehicle(id="v1", capacity_kg=15.0, max_range_km=50.0),
        Vehicle(id="v2", capacity_kg=15.0, max_range_km=50.0),
    ]


@pytest.fixture
def sample_problem(sample_deliveries, sample_vehicles, sample_depot) -> RoutingProblem:
    return RoutingProblem(
        deliveries=sample_deliveries, vehicles=sample_vehicles, depot=sample_depot
    )
