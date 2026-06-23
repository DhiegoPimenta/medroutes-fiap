"""
MedRoutes - Interface Streamlit principal.

Permite cadastrar entregas (medicamentos criticos ou insumos regulares),
configurar a frota de veiculos, rodar o Algoritmo Genetico para otimizar
as rotas, visualizar o resultado em um mapa Folium e interagir com o
Claude (Anthropic) para gerar instrucoes, relatorios e responder perguntas
sobre as rotas.
"""

from __future__ import annotations

import os
import random
import sys

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


def _init_session_state() -> None:
    defaults = {
        "deliveries": [],
        "vehicles": [],
        "depot": None,
        "ga_result": None,
        "qa_history": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _geocode_with_feedback(service: GeocodingService, address: str) -> tuple[float, float] | None:
    try:
        with st.spinner(f"Geocodificando '{address}'..."):
            result = service.geocode_address(address)
        return (result.latitude, result.longitude)
    except GeocodingError as error:
        st.error(str(error))
        return None


def render_sidebar_setup() -> None:
    """Cadastro do deposito, entregas e veiculos na barra lateral."""
    st.sidebar.header("1. Deposito (origem/retorno)")
    depot_address = st.sidebar.text_input("Endereco do deposito", key="depot_address_input")
    if st.sidebar.button("Definir deposito", use_container_width=True):
        service = GeocodingService()
        coords = _geocode_with_feedback(service, depot_address)
        if coords:
            st.session_state["depot"] = DepotLocation(
                address=depot_address, latitude=coords[0], longitude=coords[1]
            )
            st.sidebar.success("Deposito definido!")

    if st.session_state["depot"]:
        st.sidebar.caption(f"Deposito atual: {st.session_state['depot'].address}")

    st.sidebar.divider()
    st.sidebar.header("2. Cadastrar entrega")
    with st.sidebar.form("delivery_form", clear_on_submit=True):
        address = st.text_input("Endereco da entrega")
        delivery_type_label = st.selectbox(
            "Tipo", ["Medicamento critico", "Insumo regular"]
        )
        weight_kg = st.number_input("Peso/volume (kg)", min_value=0.1, value=5.0, step=0.5)
        submitted = st.form_submit_button("Adicionar entrega")

        if submitted and address:
            service = GeocodingService()
            coords = _geocode_with_feedback(service, address)
            if coords:
                delivery_type = (
                    DeliveryType.CRITICAL_MEDICATION
                    if delivery_type_label == "Medicamento critico"
                    else DeliveryType.REGULAR_SUPPLY
                )
                new_delivery = Delivery(
                    id=f"d{len(st.session_state['deliveries'])}",
                    address=address,
                    delivery_type=delivery_type,
                    weight_kg=weight_kg,
                    latitude=coords[0],
                    longitude=coords[1],
                )
                st.session_state["deliveries"].append(new_delivery)
                st.sidebar.success(f"Entrega '{address}' adicionada!")

    st.sidebar.divider()
    st.sidebar.header("3. Configurar veiculos")
    num_vehicles = st.sidebar.number_input("Numero de veiculos", min_value=1, max_value=20, value=2)
    default_capacity = st.sidebar.number_input("Capacidade de carga por veiculo (kg)", min_value=1.0, value=50.0)
    default_range = st.sidebar.number_input("Autonomia maxima por veiculo (km)", min_value=1.0, value=100.0)

    if st.sidebar.button("Aplicar configuracao de veiculos", use_container_width=True):
        st.session_state["vehicles"] = [
            Vehicle(id=f"v{i}", capacity_kg=default_capacity, max_range_km=default_range)
            for i in range(int(num_vehicles))
        ]
        st.sidebar.success(f"{int(num_vehicles)} veiculos configurados!")


def render_current_data() -> None:
    st.subheader("Dados cadastrados")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Entregas**")
        deliveries = st.session_state["deliveries"]
        if deliveries:
            st.dataframe(
                [
                    {
                        "ID": d.id,
                        "Endereco": d.address,
                        "Tipo": "Critico" if d.is_critical else "Regular",
                        "Peso (kg)": d.weight_kg,
                    }
                    for d in deliveries
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhuma entrega cadastrada ainda.")

    with col2:
        st.markdown("**Veiculos**")
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
        else:
            st.info("Nenhum veiculo configurado ainda.")


def render_optimization_panel() -> None:
    st.subheader("Otimizacao das rotas (Algoritmo Genetico)")

    col1, col2, col3 = st.columns(3)
    with col1:
        population_size = st.number_input("Tamanho da populacao", min_value=10, max_value=500, value=80)
    with col2:
        num_generations = st.number_input("Numero de geracoes", min_value=10, max_value=1000, value=150)
    with col3:
        mutation_rate = st.slider("Taxa de mutacao", min_value=0.0, max_value=1.0, value=0.15)

    can_run = bool(
        st.session_state["deliveries"] and st.session_state["vehicles"] and st.session_state["depot"]
    )

    if not can_run:
        st.warning("Cadastre ao menos uma entrega, um veiculo e defina o deposito antes de otimizar.")

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
        with st.spinner("Executando Algoritmo Genetico..."):
            ga = GeneticAlgorithm(problem, config)
            result = ga.run()

        st.session_state["ga_result"] = result
        st.session_state["problem"] = problem
        st.success(f"Otimizacao concluida! Fitness final: {result.best_fitness:.2f}")


def _compute_random_baseline_distance(problem: RoutingProblem) -> float:
    """Distancia total de uma rota aleatoria (nao otimizada), para comparacao."""
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

    st.subheader("Resultado da otimizacao")

    depot_coords = problem.depot.coordinates
    total_distance = sum(r.distance_km(depot_coords) for r in result.best_routes)

    col1, col2, col3 = st.columns(3)
    col1.metric("Distancia total", f"{total_distance:.1f} km")
    col2.metric("Veiculos utilizados", sum(1 for r in result.best_routes if r.deliveries))
    col3.metric("Tempo de otimizacao", f"{result.elapsed_seconds:.2f} s")

    route_map = build_route_map(result.best_routes, problem.depot)
    st_folium(route_map, width=None, height=500)

    st.divider()
    render_llm_panel(result, problem, total_distance)


def render_llm_panel(result, problem: RoutingProblem, total_distance: float) -> None:
    st.subheader("Assistente Claude")

    if not os.getenv("ANTHROPIC_API_KEY"):
        st.info(
            "Defina ANTHROPIC_API_KEY no arquivo .env para habilitar instrucoes, "
            "relatorios e perguntas em linguagem natural via Claude."
        )
        return

    client = ClaudeClient()
    tab1, tab2, tab3 = st.tabs(["Instrucoes por motorista", "Relatorio de eficiencia", "Perguntas sobre as rotas"])

    with tab1:
        active_routes = [r for r in result.best_routes if r.deliveries]
        if active_routes:
            vehicle_labels = [r.vehicle.label for r in active_routes]
            selected_label = st.selectbox("Selecione o veiculo", vehicle_labels)
            selected_route = next(r for r in active_routes if r.vehicle.label == selected_label)
            if st.button("Gerar instrucoes"):
                try:
                    with st.spinner("Gerando instrucoes com Claude..."):
                        instructions = client.generate_driver_instructions(selected_route, problem.depot)
                    st.markdown(instructions)
                except ClaudeClientError as error:
                    st.error(str(error))

    with tab2:
        if st.button("Gerar relatorio de eficiencia"):
            baseline_distance = _compute_random_baseline_distance(problem)
            metrics = RouteEfficiencyMetrics(
                total_distance_km=total_distance,
                random_baseline_distance_km=baseline_distance,
                num_vehicles_used=sum(1 for r in result.best_routes if r.deliveries),
                num_deliveries=len(problem.deliveries),
                num_critical_deliveries=sum(1 for d in problem.deliveries if d.is_critical),
                estimated_time_hours=total_distance / 40.0,  # estimativa: 40km/h media
            )
            try:
                with st.spinner("Gerando relatorio com Claude..."):
                    report = client.generate_efficiency_report(metrics)
                st.markdown(report)
            except ClaudeClientError as error:
                st.error(str(error))

    with tab3:
        question = st.text_input("Pergunte algo sobre as rotas (ex.: 'qual entrega e mais urgente?')")
        if st.button("Perguntar") and question:
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
    st.title("🚑 MedRoutes")
    st.caption("Otimizacao de rotas para distribuicao de medicamentos e insumos")

    render_sidebar_setup()
    render_current_data()
    st.divider()
    render_optimization_panel()
    render_results()


if __name__ == "__main__":
    main()
