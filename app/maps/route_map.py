"""
Visualizacao das rotas otimizadas em um mapa interativo Folium.

Cada veiculo recebe uma cor distinta para sua rota. Os marcadores de
entrega sao diferenciados por prioridade: medicamentos criticos usam um
icone de alerta vermelho, insumos regulares usam um icone azul padrao.
O deposito e marcado com um icone de casa/home.
"""

from __future__ import annotations

import folium

from app.genetic.fitness import VehicleRoute
from app.models.delivery import DepotLocation

# paleta de cores ciclica para diferenciar rotas de veiculos no mapa
ROUTE_COLORS = [
    "#1f77b4",  # azul
    "#d62728",  # vermelho
    "#2ca02c",  # verde
    "#ff7f0e",  # laranja
    "#9467bd",  # roxo
    "#8c564b",  # marrom
    "#e377c2",  # rosa
    "#17becf",  # ciano
]


def _color_for_vehicle(index: int) -> str:
    return ROUTE_COLORS[index % len(ROUTE_COLORS)]


def build_route_map(
    routes: list[VehicleRoute],
    depot: DepotLocation,
    zoom_start: int = 12,
) -> folium.Map:
    """Constroi um mapa Folium com as rotas otimizadas de cada veiculo.

    Args:
        routes: Rotas decodificadas e otimizadas pelo Algoritmo Genetico.
        depot: Localizacao do deposito (ponto de partida/retorno).
        zoom_start: Nivel de zoom inicial do mapa.

    Returns:
        Um objeto folium.Map pronto para renderizacao (ex.: via streamlit-folium).
    """
    depot_coords = depot.coordinates
    route_map = folium.Map(location=depot_coords, zoom_start=zoom_start, tiles="OpenStreetMap")

    folium.Marker(
        location=depot_coords,
        popup="Deposito Central",
        tooltip="Deposito (origem/retorno)",
        icon=folium.Icon(color="black", icon="home", prefix="fa"),
    ).add_to(route_map)

    for vehicle_index, route in enumerate(routes):
        if not route.deliveries:
            continue

        color = _color_for_vehicle(vehicle_index)
        path_points = [depot_coords]

        for stop_order, delivery in enumerate(route.deliveries, start=1):
            path_points.append(delivery.coordinates)

            icon_color = "red" if delivery.is_critical else "blue"
            icon_symbol = "exclamation-triangle" if delivery.is_critical else "box"
            priority_label = "CRITICO" if delivery.is_critical else "Regular"

            popup_html = (
                f"<b>Parada {stop_order}</b> - {route.vehicle.label}<br>"
                f"Entrega: {delivery.label}<br>"
                f"Prioridade: {priority_label}<br>"
                f"Peso: {delivery.weight_kg:.1f} kg"
            )
            folium.Marker(
                location=delivery.coordinates,
                popup=popup_html,
                tooltip=f"{route.vehicle.label} - parada {stop_order} ({priority_label})",
                icon=folium.Icon(color=icon_color, icon=icon_symbol, prefix="fa"),
            ).add_to(route_map)

        path_points.append(depot_coords)

        folium.PolyLine(
            locations=path_points,
            color=color,
            weight=4,
            opacity=0.8,
            tooltip=(
                f"{route.vehicle.label} | "
                f"{len(route.deliveries)} entregas | "
                f"{route.total_weight_kg:.1f} kg | "
                f"{route.distance_km(depot_coords):.1f} km"
            ),
        ).add_to(route_map)

    return route_map
