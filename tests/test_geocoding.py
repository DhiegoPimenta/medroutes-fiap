"""Testes do servico de geocodificacao (com mock do Nominatim, sem chamadas reais)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.geocoding import GeocodingError, GeocodingService
from app.models.delivery import Delivery, DeliveryType


@pytest.fixture
def mock_location():
    location = MagicMock()
    location.latitude = -23.5505
    location.longitude = -46.6333
    location.address = "Praca da Se, Sao Paulo, SP, Brasil"
    return location


def test_geocode_address_returns_result_on_success(mock_location):
    with patch("app.geocoding.Nominatim") as mock_nominatim_cls:
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim_cls.return_value = mock_geolocator

        service = GeocodingService(delay_seconds=0)
        result = service.geocode_address("Praca da Se, Sao Paulo")

        assert result.latitude == -23.5505
        assert result.longitude == -46.6333
        mock_geolocator.geocode.assert_called_once_with("Praca da Se, Sao Paulo")


def test_geocode_address_raises_for_empty_string():
    service = GeocodingService(delay_seconds=0)
    with pytest.raises(GeocodingError):
        service.geocode_address("")


def test_geocode_address_raises_when_not_found():
    with patch("app.geocoding.Nominatim") as mock_nominatim_cls:
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = None
        mock_nominatim_cls.return_value = mock_geolocator

        service = GeocodingService(delay_seconds=0, max_retries=1)
        with pytest.raises(GeocodingError):
            service.geocode_address("Endereco inexistente xyz123")


def test_geocode_delivery_fills_coordinates(mock_location):
    with patch("app.geocoding.Nominatim") as mock_nominatim_cls:
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim_cls.return_value = mock_geolocator

        service = GeocodingService(delay_seconds=0)
        delivery = Delivery(
            id="d1", address="Praca da Se", delivery_type=DeliveryType.REGULAR_SUPPLY, weight_kg=5
        )
        service.geocode_delivery(delivery)

        assert delivery.is_geocoded
        assert delivery.latitude == -23.5505
        assert delivery.longitude == -46.6333
