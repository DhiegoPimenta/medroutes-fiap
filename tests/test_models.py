"""Testes das dataclasses de dominio (Delivery, Vehicle, RoutingProblem)."""

from __future__ import annotations

import pytest

from app.models.delivery import Delivery, DeliveryType, DepotLocation, RoutingProblem, Vehicle


def test_delivery_rejects_non_positive_weight():
    with pytest.raises(ValueError):
        Delivery(id="d1", address="Rua X", delivery_type=DeliveryType.REGULAR_SUPPLY, weight_kg=0)


def test_delivery_is_critical_property():
    critical = Delivery(
        id="d1", address="Rua X", delivery_type=DeliveryType.CRITICAL_MEDICATION, weight_kg=1
    )
    regular = Delivery(
        id="d2", address="Rua Y", delivery_type=DeliveryType.REGULAR_SUPPLY, weight_kg=1
    )
    assert critical.is_critical is True
    assert regular.is_critical is False


def test_delivery_coordinates_raises_when_not_geocoded():
    delivery = Delivery(id="d1", address="Rua X", delivery_type=DeliveryType.REGULAR_SUPPLY, weight_kg=1)
    with pytest.raises(ValueError):
        _ = delivery.coordinates


def test_vehicle_rejects_non_positive_capacity():
    with pytest.raises(ValueError):
        Vehicle(id="v1", capacity_kg=0, max_range_km=10)


def test_routing_problem_validate_fails_without_deliveries(sample_vehicles, sample_depot):
    problem = RoutingProblem(deliveries=[], vehicles=sample_vehicles, depot=sample_depot)
    with pytest.raises(ValueError):
        problem.validate()


def test_routing_problem_validate_fails_when_capacity_insufficient(
    sample_deliveries, sample_depot
):
    tiny_vehicle = Vehicle(id="v1", capacity_kg=1.0, max_range_km=50.0)
    problem = RoutingProblem(deliveries=sample_deliveries, vehicles=[tiny_vehicle], depot=sample_depot)
    with pytest.raises(ValueError):
        problem.validate()


def test_routing_problem_validate_succeeds_with_valid_data(sample_problem):
    sample_problem.validate()  # nao deve lancar excecao
