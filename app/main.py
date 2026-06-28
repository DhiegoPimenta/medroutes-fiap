"""
MedRoutes - Interface Streamlit principal.

Permite cadastrar entregas (medicamentos críticos ou insumos regulares),
configurar a frota de veículos, rodar o Algoritmo Genético para otimizar
as rotas, visualizar o resultado em um mapa Folium e interagir com o
Claude (Anthropic) para gerar instruções, relatórios e responder perguntas
sobre as rotas.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from app.genetic.algorithm import GeneticAlgorithm, GeneticAlgorithmConfig
from app.genetic.fitness import FitnessWeights, evaluate_fitness
from app.genetic.operators import create_random_chromosome
from app.geocoding import GeocodingError, GeocodingService
from app.llm.claude_client import ClaudeClient, ClaudeClientError, RouteEfficiencyMetrics
from app.maps.route_map import build_route_map
from app.models.delivery import Delivery, DeliveryType, DepotLocation, RoutingProblem, Vehicle

load_dotenv()

st.set_page_config(page_title="MedRoutes", page_icon="🚑", layout="wide")

_THEME_CSS_PATH = Path(__file__).parent / "ui" / "theme.css"


def _inject_theme() -> None:
    """Injeta o CSS de refinamento visual (paleta oficial da marca)."""
    try:
        css = _THEME_CSS_PATH.read_text(encoding="utf-8")
    except OSError:
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _sidebar_step(number: int, title: str) -> None:
    """Renderiza um cabeçalho de etapa da sidebar com badge numerado (stepper)."""
    st.sidebar.markdown(
        f'<div class="step-header">'
        f'<span class="step-badge">{number}</span>'
        f'<span class="step-title">{title}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _init_session_state() -> None:
    defaults = {
        "deliveries": [],
        "vehicles": [],
        "depot": None,
        "ga_result": None,
        "qa_history": [],
        "driver_instructions": {},  # {vehicle_label: texto}
        "efficiency_report": None,
        "delivery_counter": 0,  # contador monotônico para IDs únicos de entrega
        "vehicle_counter": 0,  # contador monotônico para IDs únicos de veículo
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _geocode_with_feedback(service: GeocodingService, address: str) -> tuple[float, float] | None:
    try:
        result = service.geocode_address(address)
        return (result.latitude, result.longitude)
    except GeocodingError as error:
        st.sidebar.error(str(error))
        return None


def render_sidebar_setup() -> None:
    """Cadastro do depósito, entregas e veículos na barra lateral."""
    _sidebar_step(1, "Depósito (origem/retorno)")
    depot_address = st.sidebar.text_input("Endereço do depósito", key="depot_address_input")
    if st.sidebar.button(
        "Definir depósito",
        use_container_width=True,
        disabled=not depot_address.strip(),
    ):
        service = GeocodingService()
        coords = _geocode_with_feedback(service, depot_address)
        if coords:
            st.session_state["depot"] = DepotLocation(
                address=depot_address, latitude=coords[0], longitude=coords[1]
            )
            st.sidebar.success("Depósito definido!")

    if st.session_state["depot"]:
        st.sidebar.caption(f"Depósito atual: {st.session_state['depot'].address}")

    st.sidebar.divider()
    _sidebar_step(2, "Cadastrar entrega")
    with st.sidebar.form("delivery_form", clear_on_submit=True):
        address = st.text_input("Endereço da entrega")
        delivery_type_label = st.selectbox(
            "Tipo", ["Medicamento crítico", "Insumo regular"]
        )
        weight_kg = st.number_input("Peso/volume (kg)", min_value=0.1, value=5.0, step=0.5)
        submitted = st.form_submit_button(
            "Adicionar entrega", use_container_width=True, type="primary"
        )

        if submitted and address:
            service = GeocodingService()
            coords = _geocode_with_feedback(service, address)
            if coords:
                delivery_type = (
                    DeliveryType.CRITICAL_MEDICATION
                    if delivery_type_label == "Medicamento crítico"
                    else DeliveryType.REGULAR_SUPPLY
                )
                new_delivery = Delivery(
                    id=f"d{st.session_state['delivery_counter']}",
                    address=address,
                    delivery_type=delivery_type,
                    weight_kg=weight_kg,
                    latitude=coords[0],
                    longitude=coords[1],
                )
                st.session_state["delivery_counter"] += 1
                st.session_state["deliveries"].append(new_delivery)
                st.sidebar.success(f"Entrega '{address}' adicionada!", icon="📦")
        elif submitted and not address:
            st.sidebar.warning("Informe o endereço da entrega antes de adicionar.")

    if st.session_state["deliveries"]:
        st.sidebar.caption(f"Entregas cadastradas: {len(st.session_state['deliveries'])}")

    st.sidebar.divider()
    _sidebar_step(3, "Cadastrar veículo")
    with st.sidebar.form("vehicle_form", clear_on_submit=True):
        capacity_kg = st.number_input("Capacidade de carga (kg)", min_value=1.0, value=50.0, step=1.0)
        max_range_km = st.number_input("Autonomia máxima (km)", min_value=1.0, value=100.0, step=1.0)
        submitted = st.form_submit_button(
            "Adicionar veículo", use_container_width=True, type="primary"
        )

        if submitted:
            new_vehicle = Vehicle(
                id=f"v{st.session_state['vehicle_counter']}",
                capacity_kg=capacity_kg,
                max_range_km=max_range_km,
            )
            st.session_state["vehicle_counter"] += 1
            st.session_state["vehicles"].append(new_vehicle)
            st.sidebar.success(
                f"Veículo adicionado: {capacity_kg:.0f}kg / {max_range_km:.0f}km", icon="🚐"
            )

    if st.session_state["vehicles"]:
        st.sidebar.caption(f"Frota atual: {len(st.session_state['vehicles'])} veículo(s)")


def _remove_delivery(delivery_id: str) -> None:
    """Remove a entrega com o ID informado e invalida o resultado da otimização."""
    st.session_state["deliveries"] = [
        d for d in st.session_state["deliveries"] if d.id != delivery_id
    ]
    # a rota otimizada anterior não corresponde mais às entregas atuais
    st.session_state["ga_result"] = None


def _remove_vehicle(vehicle_id: str) -> None:
    """Remove o veículo com o ID informado e invalida o resultado da otimização."""
    st.session_state["vehicles"] = [
        v for v in st.session_state["vehicles"] if v.id != vehicle_id
    ]
    # a rota otimizada anterior não corresponde mais à frota atual
    st.session_state["ga_result"] = None


def render_current_data() -> None:
    st.subheader("📋 Dados cadastrados")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**📦 Entregas**")
        deliveries = st.session_state["deliveries"]
        if deliveries:
            st.dataframe(
                [
                    {
                        "ID": d.id,
                        "Endereço": d.address,
                        "Tipo": "🔴 Crítico" if d.is_critical else "🔵 Regular",
                        "Peso (kg)": d.weight_kg,
                    }
                    for d in deliveries
                ],
                use_container_width=True,
                hide_index=True,
            )

            with st.expander("⚙️ Gerenciar entregas", expanded=False):
                options = {f"{d.id} — {d.address}": d.id for d in deliveries}
                select_col, button_col = st.columns([3, 1], vertical_alignment="bottom")
                with select_col:
                    selected_label = st.selectbox(
                        "Selecione a entrega",
                        list(options.keys()),
                        key="remove_delivery_select",
                    )
                with button_col:
                    if st.button(
                        "🗑️ Remover",
                        key="remove_delivery_btn",
                        use_container_width=True,
                    ):
                        _remove_delivery(options[selected_label])
                        st.rerun()

                if st.button(
                    "Limpar todas as entregas",
                    key="clear_deliveries_btn",
                    type="secondary",
                    use_container_width=True,
                ):
                    st.session_state["deliveries"] = []
                    st.session_state["ga_result"] = None
                    st.rerun()
        else:
            st.info("Nenhuma entrega cadastrada ainda.")

    with col2:
        st.markdown("**🚐 Veículos**")
        vehicles = st.session_state["vehicles"]
        if vehicles:
            st.dataframe(
                [
                    {"ID": v.id, "Capacidade (kg)": v.capacity_kg, "Autonomia (km)": v.max_range_km}
                    for v in vehicles
                ],
                use_container_width=True,
                hide_index=True,
            )

            with st.expander("⚙️ Gerenciar veículos", expanded=False):
                options = {f"{v.id} — {v.capacity_kg:.0f}kg / {v.max_range_km:.0f}km": v.id for v in vehicles}
                select_col, button_col = st.columns([3, 1], vertical_alignment="bottom")
                with select_col:
                    selected_label = st.selectbox(
                        "Selecione o veículo",
                        list(options.keys()),
                        key="remove_vehicle_select",
                    )
                with button_col:
                    if st.button(
                        "🗑️ Remover",
                        key="remove_vehicle_btn",
                        use_container_width=True,
                    ):
                        _remove_vehicle(options[selected_label])
                        st.rerun()

                if st.button(
                    "Limpar todos os veículos",
                    key="clear_vehicles_btn",
                    type="secondary",
                    use_container_width=True,
                ):
                    st.session_state["vehicles"] = []
                    st.session_state["ga_result"] = None
                    st.rerun()
        else:
            st.info("Nenhum veículo configurado ainda.")


def render_optimization_panel() -> None:
    st.subheader("⚙️ Otimização das rotas (Algoritmo Genético)")

    col1, col2, col3 = st.columns(3)
    with col1:
        population_size = st.number_input("Tamanho da população", min_value=10, max_value=500, value=80)
    with col2:
        num_generations = st.number_input("Número de gerações", min_value=10, max_value=1000, value=150)
    with col3:
        mutation_rate = st.slider("Taxa de mutação", min_value=0.0, max_value=1.0, value=0.15)

    depot_ok = st.session_state["depot"] is not None
    deliveries_ok = len(st.session_state["deliveries"]) >= 2
    vehicles_ok = len(st.session_state["vehicles"]) >= 1
    can_run = depot_ok and deliveries_ok and vehicles_ok

    if not depot_ok:
        st.warning("Defina o endereço do depósito (origem) na barra lateral antes de otimizar.")
    if len(st.session_state["deliveries"]) == 0:
        st.warning("Cadastre ao menos duas entregas na barra lateral antes de otimizar.")
    elif len(st.session_state["deliveries"]) == 1:
        st.warning("O Algoritmo Genético requer ao menos 2 entregas para otimizar rotas. Cadastre mais uma entrega.")
    if not vehicles_ok:
        st.warning("Configure ao menos um veículo na barra lateral antes de otimizar.")

    if st.button("Otimizar rotas", type="primary", disabled=not can_run):
        problem = RoutingProblem(
            deliveries=st.session_state["deliveries"],
            vehicles=st.session_state["vehicles"],
            depot=st.session_state["depot"],
        )
        try:
            problem.validate()
        except ValueError as error:
            st.error(str(error))
            return

        config = GeneticAlgorithmConfig(
            population_size=int(population_size),
            num_generations=int(num_generations),
            mutation_rate=float(mutation_rate),
        )
        try:
            with st.spinner("Executando Algoritmo Genético..."):
                ga = GeneticAlgorithm(problem, config)
                result = ga.run()
        except Exception as error:  # falha inesperada no AG: não derrubar a UI
            st.error(
                "Não foi possível concluir a otimização. "
                f"Detalhe técnico: {error}"
            )
            return

        st.session_state["ga_result"] = result
        st.session_state["problem"] = problem
        st.session_state["driver_instructions"] = {}
        st.session_state["efficiency_report"] = None
        st.session_state["qa_history"] = []
        st.rerun()


def _compute_random_baseline_distance(problem: RoutingProblem) -> float:
    """Distância total de uma rota aleatória (não otimizada), para comparação."""
    rng = random.Random(0)
    chromosome = create_random_chromosome(len(problem.deliveries), rng=rng)
    from app.genetic.fitness import decode_chromosome

    routes = decode_chromosome(chromosome, problem)
    return sum(r.distance_km(problem.depot.coordinates) for r in routes)


def render_results() -> None:
    result = st.session_state.get("ga_result")
    problem = st.session_state.get("problem")
    if not result or not problem:
        return

    st.subheader("🗺️ Resultado da otimização")
    st.success(f"Otimização concluída! Fitness final: {result.best_fitness:.2f}")

    depot_coords = problem.depot.coordinates
    total_distance = sum(r.distance_km(depot_coords) for r in result.best_routes)

    col1, col2, col3 = st.columns(3)
    col1.metric("Distância total", f"{total_distance:.1f} km")
    col2.metric("Veículos utilizados", sum(1 for r in result.best_routes if r.deliveries))
    col3.metric("Tempo de otimização", f"{result.elapsed_seconds:.2f} s")

    st.markdown('<div class="map-label">Rotas otimizadas</div>', unsafe_allow_html=True)
    route_map = build_route_map(result.best_routes, problem.depot)
    st_folium(route_map, width=None, height=520)

    st.divider()
    render_llm_panel(result, problem, total_distance)


def render_llm_panel(result, problem: RoutingProblem, total_distance: float) -> None:
    st.subheader("🤖 Assistente Claude")

    if not os.getenv("ANTHROPIC_API_KEY"):
        st.info(
            "Defina ANTHROPIC_API_KEY no arquivo .env para habilitar instruções, "
            "relatórios e perguntas em linguagem natural via Claude."
        )
        return

    client = ClaudeClient()
    tab1, tab2, tab3 = st.tabs(["Instruções por motorista", "Relatório de eficiência", "Perguntas sobre as rotas"])

    with tab1:
        active_routes = [r for r in result.best_routes if r.deliveries]
        if active_routes:
            vehicle_labels = [r.vehicle.label for r in active_routes]
            selected_label = st.selectbox("Selecione o veículo", vehicle_labels)
            selected_route = next(r for r in active_routes if r.vehicle.label == selected_label)
            if st.button("Gerar instruções", type="primary", use_container_width=True):
                try:
                    with st.spinner("Gerando instruções com Claude..."):
                        instructions = client.generate_driver_instructions(selected_route, problem.depot)
                    st.session_state["driver_instructions"][selected_label] = instructions
                except ClaudeClientError as error:
                    st.error(str(error))
            if selected_label in st.session_state["driver_instructions"]:
                st.markdown(st.session_state["driver_instructions"][selected_label])

    with tab2:
        if st.button("Gerar relatório de eficiência", type="primary", use_container_width=True):
            baseline_distance = _compute_random_baseline_distance(problem)
            metrics = RouteEfficiencyMetrics(
                total_distance_km=total_distance,
                random_baseline_distance_km=baseline_distance,
                num_vehicles_used=sum(1 for r in result.best_routes if r.deliveries),
                num_deliveries=len(problem.deliveries),
                num_critical_deliveries=sum(1 for d in problem.deliveries if d.is_critical),
                estimated_time_hours=total_distance / 40.0,  # estimativa: 40km/h média
            )
            try:
                with st.spinner("Gerando relatório com Claude..."):
                    st.session_state["efficiency_report"] = client.generate_efficiency_report(metrics)
            except ClaudeClientError as error:
                st.error(str(error))
        if st.session_state["efficiency_report"]:
            st.markdown(st.session_state["efficiency_report"])

    with tab3:
        question = st.text_input("Pergunte algo sobre as rotas (ex.: 'qual entrega é mais urgente?')")
        if st.button("Perguntar", type="primary", use_container_width=True) and question:
            try:
                with st.spinner("Consultando Claude..."):
                    answer = client.answer_question_about_routes(question, result.best_routes, problem.depot)
                st.session_state["qa_history"].append((question, answer))
            except ClaudeClientError as error:
                st.error(str(error))

        for past_question, past_answer in reversed(st.session_state["qa_history"]):
            with st.chat_message("user"):
                st.write(past_question)
            with st.chat_message("assistant"):
                st.write(past_answer)


def main() -> None:
    _init_session_state()
    _inject_theme()
    st.markdown(
        '<div class="medroutes-hero">'
        '<div class="medroutes-hero__icon">🚑</div>'
        "<div>"
        '<h1 class="medroutes-hero__title">MedRoutes</h1>'
        '<p class="medroutes-hero__subtitle">'
        "Otimização de rotas para distribuição de medicamentos e insumos"
        "</p>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    render_sidebar_setup()
    render_current_data()
    st.divider()
    render_optimization_panel()
    render_results()


if __name__ == "__main__":
    main()
