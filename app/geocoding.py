"""
Geocodificação de endereços usando Nominatim (OpenStreetMap), gratuito.

Converte endereços textuais informados pelo usuário em coordenadas
(latitude, longitude) usadas pelo Algoritmo Genético e pelo mapa Folium.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from app.models.delivery import Delivery, DepotLocation


class GeocodingError(Exception):
    """Lançado quando um endereço não pode ser geocodificado."""


@dataclass
class GeocodingResult:
    """Resultado de uma geocodificação bem-sucedida."""

    address: str
    latitude: float
    longitude: float
    display_name: str


class GeocodingService:
    """Encapsula chamadas ao Nominatim com retry simples e User-Agent obrigatório.

    O Nominatim exige um User-Agent identificável por política de uso
    (https://operations.osmfoundation.org/policies/nominatim/) e recomenda
    no máximo 1 requisição por segundo, por isso o pequeno `delay_seconds`
    entre chamadas sucessivas.
    """

    def __init__(
        self,
        user_agent: Optional[str] = None,
        delay_seconds: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.user_agent = user_agent or os.getenv(
            "NOMINATIM_USER_AGENT", "medroutes-fiap-tech-challenge"
        )
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self._geolocator = Nominatim(user_agent=self.user_agent)

    def geocode_address(self, address: str) -> GeocodingResult:
        """Geocodifica um único endereço textual.

        Lança GeocodingError se o endereço não for encontrado após as
        tentativas de retry, ou se o serviço do Nominatim falhar.
        """
        if not address or not address.strip():
            raise GeocodingError("Endereço vazio não pode ser geocodificado")

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                location = self._geolocator.geocode(address)
                if location is None:
                    raise GeocodingError(f"Endereço não encontrado: '{address}'")
                return GeocodingResult(
                    address=address,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    display_name=location.address,
                )
            except (GeocoderTimedOut, GeocoderServiceError) as error:
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(self.delay_seconds)
                continue

        raise GeocodingError(
            f"Falha ao geocodificar '{address}' após {self.max_retries} tentativas"
        ) from last_error

    def geocode_delivery(self, delivery: Delivery) -> Delivery:
        """Geocodifica uma entrega in-place e a retorna (lat/lon preenchidos)."""
        result = self.geocode_address(delivery.address)
        delivery.latitude = result.latitude
        delivery.longitude = result.longitude
        time.sleep(self.delay_seconds)
        return delivery

    def geocode_depot(self, depot: DepotLocation) -> DepotLocation:
        """Geocodifica o depósito in-place e o retorna (lat/lon preenchidos)."""
        result = self.geocode_address(depot.address)
        depot.latitude = result.latitude
        depot.longitude = result.longitude
        time.sleep(self.delay_seconds)
        return depot
