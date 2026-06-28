"""Testes do servico de geocodificacao (com mock do Nominatim, sem chamadas reais)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

from app.geocoding import (
    GeocodingError,
    GeocodingService,
    _geocode_via_awesomeapi,
    _normalize_address,
    _simplify_address,
)
from app.models.delivery import Delivery, DeliveryType


@pytest.fixture
def mock_location():
    location = MagicMock()
    location.latitude = -23.5505
    location.longitude = -46.6333
    location.address = "Praca da Se, Sao Paulo, SP, Brasil"
    return location


# ---------------------------------------------------------------------------
# Normalização de endereço
# ---------------------------------------------------------------------------


def test_normalize_expands_street_abbreviation():
    assert _normalize_address("R. das Flores, 100") == "Rua das Flores, 100"


def test_normalize_expands_avenue_abbreviation():
    assert _normalize_address("Av. Paulista, 1000") == "Avenida Paulista, 1000"


def test_normalize_expands_title_abbreviations():
    # "Profa." deve virar "Professora" sem ser parcialmente pego por "Prof."
    assert _normalize_address("R. Profa. Maria Flaquer, 367") == "Rua Professora Maria Flaquer, 367"
    assert _normalize_address("Av. Prof. Ascendino Reis") == "Avenida Professor Ascendino Reis"
    assert _normalize_address("R. Dr. Arnaldo") == "Rua Doutor Arnaldo"


def test_normalize_removes_cep():
    result = _normalize_address("Rua das Flores, 100, 01310-100")
    assert "01310" not in result


def test_normalize_removes_apartment_complement():
    result = _normalize_address("Rua das Flores, 100, Apto 42, São Paulo")
    assert "apto" not in result.lower()
    assert "São Paulo" in result


def test_normalize_removes_bloco_complement():
    result = _normalize_address("Av. Brasil, 500, Bloco B, Rio de Janeiro")
    assert "Bloco" not in result
    assert "Rio de Janeiro" in result


def test_normalize_collapses_extra_spaces():
    result = _normalize_address("Rua   das   Flores")
    assert "  " not in result


# ---------------------------------------------------------------------------
# Simplificação de endereço (fallback)
# ---------------------------------------------------------------------------


def test_simplify_removes_number_and_keeps_street_and_city():
    simplified = _simplify_address("Rua Prof. Freitas Julião, 141, Jardim Luso, São Paulo")
    assert "141" not in simplified
    assert "Rua Prof. Freitas Julião" in simplified


def test_simplify_handles_dash_separated_state():
    simplified = _simplify_address("Rua das Flores, 10 - Jardim Luso - São Paulo - SP")
    assert "SP" not in simplified


# ---------------------------------------------------------------------------
# Geocoding com mock
# ---------------------------------------------------------------------------


def test_geocode_address_returns_result_on_success(mock_location):
    with patch("app.geocoding.Nominatim") as mock_nominatim_cls:
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim_cls.return_value = mock_geolocator

        service = GeocodingService(delay_seconds=0)
        result = service.geocode_address("Praca da Se, Sao Paulo")

        assert result.latitude == -23.5505
        assert result.longitude == -46.6333


def test_geocode_address_passes_country_code_br(mock_location):
    with patch("app.geocoding.Nominatim") as mock_nominatim_cls:
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim_cls.return_value = mock_geolocator

        service = GeocodingService(delay_seconds=0)
        service.geocode_address("Praca da Se, Sao Paulo")

        _, kwargs = mock_geolocator.geocode.call_args
        assert kwargs.get("country_codes") == "BR"


def test_geocode_address_raises_for_empty_string():
    service = GeocodingService(delay_seconds=0)
    with pytest.raises(GeocodingError):
        service.geocode_address("")


def test_geocode_address_falls_back_to_simplified_when_full_not_found(mock_location):
    """Primeira chamada retorna None; segunda (simplificada) retorna resultado."""
    with patch("app.geocoding.Nominatim") as mock_nominatim_cls:
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.side_effect = [None, mock_location]
        mock_nominatim_cls.return_value = mock_geolocator

        service = GeocodingService(delay_seconds=0)
        result = service.geocode_address(
            "R. Prof. Freitas Julião, 141 - Jardim Luso, São Paulo - SP, 04421-050"
        )

        assert result.latitude == -23.5505
        assert mock_geolocator.geocode.call_count == 2


def test_geocode_address_falls_back_to_global_for_international_address(mock_location):
    """BR falha nas duas primeiras tentativas; busca global (sem country_codes) resolve."""
    with patch("app.geocoding.Nominatim") as mock_nominatim_cls:
        mock_geolocator = MagicMock()
        # 1ª e 2ª chamadas (BR) retornam None; 3ª (global) encontra
        mock_geolocator.geocode.side_effect = [None, None, mock_location]
        mock_nominatim_cls.return_value = mock_geolocator

        service = GeocodingService(delay_seconds=0)
        result = service.geocode_address("10 Downing Street, London, UK")

        assert result.latitude == -23.5505
        assert mock_geolocator.geocode.call_count == 3
        # última chamada não deve ter country_codes
        last_call_kwargs = mock_geolocator.geocode.call_args_list[-1][1]
        assert "country_codes" not in last_call_kwargs


def test_geocode_via_awesomeapi_returns_none_when_no_cep_in_address():
    result = _geocode_via_awesomeapi("Avenida Paulista, São Paulo")
    assert result is None


def test_geocode_via_awesomeapi_returns_result_when_api_succeeds():
    awesomeapi_response = json.dumps({
        "cep": "09380400",
        "address": "Rua Professora Maria Josefina Kuman Fláquer",
        "district": "Jardim Silvia Maria",
        "city": "Mauá",
        "state": "SP",
        "lat": "-23.6318096",
        "lng": "-46.4776474",
    }).encode()

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = awesomeapi_response
        mock_urlopen.return_value.__enter__ = lambda s: mock_response
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = _geocode_via_awesomeapi("R. Profa. Maria Kuman Fláquer, 195, 09380-400")

    assert result is not None
    assert result.latitude == pytest.approx(-23.6318096)
    assert result.longitude == pytest.approx(-46.4776474)


def test_geocode_via_awesomeapi_returns_none_when_coords_missing():
    awesomeapi_response = json.dumps({"cep": "09380400", "city": "Mauá"}).encode()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = awesomeapi_response
        mock_urlopen.return_value.__enter__ = lambda s: mock_response
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = _geocode_via_awesomeapi("Rua X, 09380-400")
    assert result is None


def test_geocode_address_falls_back_to_awesomeapi_when_nominatim_fails(mock_location):
    """Todos os Nominatim retornam None; AwesomeAPI resolve pelo CEP no endereço."""
    awesomeapi_response = json.dumps({
        "cep": "09380400",
        "address": "Rua Professora Maria Josefina Kuman Fláquer",
        "district": "Jardim Silvia Maria",
        "city": "Mauá",
        "state": "SP",
        "lat": "-23.6318096",
        "lng": "-46.4776474",
    }).encode()

    with patch("app.geocoding.Nominatim") as mock_nominatim_cls, \
         patch("urllib.request.urlopen") as mock_urlopen:
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = None
        mock_nominatim_cls.return_value = mock_geolocator

        mock_response = MagicMock()
        mock_response.read.return_value = awesomeapi_response
        mock_urlopen.return_value.__enter__ = lambda s: mock_response
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        service = GeocodingService(delay_seconds=0)
        result = service.geocode_address(
            "R. Profa. Maria Josefina Kuman Fláquer, 195 - Mauá - SP, 09380-400"
        )

    assert result.latitude == pytest.approx(-23.6318096)
    assert result.longitude == pytest.approx(-46.4776474)


def test_geocode_address_raises_when_all_attempts_fail():
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
