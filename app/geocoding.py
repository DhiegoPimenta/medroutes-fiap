"""
Geocodificação de endereços usando Nominatim (OpenStreetMap), gratuito.

Converte endereços textuais informados pelo usuário em coordenadas
(latitude, longitude) usadas pelo Algoritmo Genético e pelo mapa Folium.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
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


# Abreviações comuns em endereços brasileiros → forma completa.
# Ordem importa: variações mais longas (ex.: "Profa.") antes das curtas ("Prof.").
_BR_ABBREVIATIONS: dict[str, str] = {
    # tipos de logradouro
    r"\bR\.\s*": "Rua ",
    r"\bAv\.\s*": "Avenida ",
    r"\bAl\.\s*": "Alameda ",
    r"\bTrav\.\s*": "Travessa ",
    r"\bEst\.\s*": "Estrada ",
    r"\bRod\.\s*": "Rodovia ",
    r"\bPça\.\s*": "Praça ",
    r"\bPc\.\s*": "Praça ",
    r"\bVl\.\s*": "Vila ",
    r"\bJd\.\s*": "Jardim ",
    r"\bBl\.\s*": "Bloco ",
    # títulos/honoríficos comuns em nomes de ruas
    r"\bProfa\.\s*": "Professora ",
    r"\bProf\.\s*": "Professor ",
    r"\bDra\.\s*": "Doutora ",
    r"\bDr\.\s*": "Doutor ",
    r"\bSta\.\s*": "Santa ",
    r"\bSto\.\s*": "Santo ",
    r"\bPe\.\s*": "Padre ",
    r"\bCel\.\s*": "Coronel ",
    r"\bGen\.\s*": "General ",
    r"\bEng\.\s*": "Engenheiro ",
}

# Partes do endereço que o Nominatim não consegue resolver (complementos)
_COMPLEMENT_PATTERN = re.compile(
    r",?\s*(apto?\.?|apartamento|bloco|bl\.?|andar|sala|conjunto|conj\.?|"
    r"loja|lote|lj\.?|casa|cs\.?|cond\.?|condomínio|edifício|ed\.?)\s+[\w\-/]+",
    re.IGNORECASE,
)

# CEP no formato 00000-000 ou 00000000
_CEP_PATTERN = re.compile(r",?\s*\d{5}-?\d{3}")


def _normalize_address(address: str) -> str:
    """Expande abreviações e remove complementos/CEP que confundem o Nominatim."""
    normalized = address.strip()

    for pattern, replacement in _BR_ABBREVIATIONS.items():
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    normalized = _COMPLEMENT_PATTERN.sub("", normalized)
    normalized = _CEP_PATTERN.sub("", normalized)

    # Colapsa espaços e vírgulas duplas geradas pela remoção
    normalized = re.sub(r",\s*,", ",", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized).strip().strip(",").strip()

    return normalized


_AWESOMEAPI_CEP_URL = "https://cep.awesomeapi.com.br/json/{cep}"
_CEP_DIGITS_PATTERN = re.compile(r"\b(\d{5})-?(\d{3})\b")


def _extract_cep(address: str) -> str | None:
    """Extrai os 8 dígitos do CEP do endereço, sem o hífen. None se não houver."""
    match = _CEP_DIGITS_PATTERN.search(address)
    return match.group(1) + match.group(2) if match else None


def _http_get_json(url: str, timeout: int = 5) -> dict | None:
    """GET simples que retorna JSON como dict, ou None em qualquer falha."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "medroutes-fiap-tech-challenge"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _geocode_via_awesomeapi(address: str) -> GeocodingResult | None:
    """Fallback via CEP usando a AwesomeAPI, que retorna lat/lng diretamente.

    Só é acionada quando os fallbacks do Nominatim falham e o endereço
    contém um CEP. Resolve ruas que o OSM não tem cadastradas. Nunca lança
    exceção — retorna None em qualquer falha.
    """
    cep = _extract_cep(address)
    if not cep:
        return None

    data = _http_get_json(_AWESOMEAPI_CEP_URL.format(cep=cep))
    if not data:
        return None

    lat = data.get("lat")
    lng = data.get("lng")
    if not lat or not lng:
        return None

    display = ", ".join(
        filter(None, [data.get("address"), data.get("district"), data.get("city"), data.get("state")])
    )
    return GeocodingResult(
        address=address,
        latitude=float(lat),
        longitude=float(lng),
        display_name=display or address,
    )


def _simplify_address(address: str) -> str:
    """Remove o número e tudo depois da primeira vírgula pós-logradouro.

    Ex.: "Rua Prof. Freitas Julião, 141 - Jardim Luso, São Paulo - SP"
         → "Rua Prof. Freitas Julião, São Paulo"
    Usado como último fallback quando o endereço completo não é encontrado.
    """
    # Mantém apenas logradouro + primeira parte geográfica útil (cidade/estado)
    parts = [p.strip() for p in address.split(",")]
    kept: list[str] = []
    for part in parts:
        # Descarta partes que parecem número isolado ou bairro com hífen
        if re.match(r"^\d+", part):
            continue
        if " - " in part:
            # "Jardim Luso - São Paulo - SP" → só "São Paulo"
            sub = [s.strip() for s in part.split(" - ")]
            kept.extend(s for s in sub if not re.match(r"^[A-Z]{2}$", s) and len(s) > 3)
        else:
            kept.append(part)
    simplified = ", ".join(kept[:2]) if len(kept) >= 2 else ", ".join(kept)
    return simplified or address


class GeocodingService:
    """Encapsula chamadas ao Nominatim com retry, normalização e fallbacks em cascata.

    Ordem de tentativas em ``geocode_address``:
      1. Endereço normalizado restrito ao Brasil (Nominatim + country_codes="BR").
      2. Endereço simplificado (sem número/complemento) restrito ao Brasil.
      3. Endereço normalizado sem restrição de país (suporte a endereços internacionais).
      4. AwesomeAPI via CEP extraído do endereço (fallback exclusivamente brasileiro,
         acionado apenas se o endereço contiver um CEP e os três anteriores falharem).

    O Nominatim exige um User-Agent identificável por política de uso
    (https://operations.osmfoundation.org/policies/nominatim/) e recomenda
    no máximo 1 requisição por segundo, por isso o pequeno ``delay_seconds``
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

    def _geocode_query(self, query: str, country_codes: str | None = "BR") -> object | None:
        """Executa uma query no Nominatim com retry para falhas de rede.

        ``country_codes=None`` remove a restrição geográfica (busca global).
        """
        last_error: Exception | None = None
        kwargs: dict = {}
        if country_codes:
            kwargs["country_codes"] = country_codes
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._geolocator.geocode(query, **kwargs)
            except (GeocoderTimedOut, GeocoderServiceError) as error:
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(self.delay_seconds)
        raise GeocodingError(
            f"Falha ao geocodificar '{query}' após {self.max_retries} tentativas"
        ) from last_error

    def geocode_address(self, address: str) -> GeocodingResult:
        """Geocodifica um endereço com normalização e fallbacks em cascata.

        Lança GeocodingError se nenhuma das quatro tentativas retornar resultado.
        """
        if not address or not address.strip():
            raise GeocodingError("Endereço vazio não pode ser geocodificado")

        normalized = _normalize_address(address)

        location = self._geocode_query(normalized, country_codes="BR")

        if location is None:
            simplified = _simplify_address(normalized)
            if simplified != normalized:
                location = self._geocode_query(simplified, country_codes="BR")

        if location is None:
            location = self._geocode_query(normalized, country_codes=None)

        if location is not None:
            return GeocodingResult(
                address=address,
                latitude=location.latitude,
                longitude=location.longitude,
                display_name=location.address,
            )

        # Fallback via CEP (resolve ruas que o OSM não tem, desde que o
        # endereço contenha CEP). AwesomeAPI retorna lat/lng diretamente.
        cep_result = _geocode_via_awesomeapi(address)
        if cep_result is not None:
            return cep_result

        raise GeocodingError(f"Endereço não encontrado: '{address}'")

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
