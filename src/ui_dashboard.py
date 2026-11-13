"""Streamlit command-centre pages for the REEFERTWIN demo."""

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.twin.demo_store import TwinDemoStore
from src.twin.scenarios import ActionStatus, ScenarioType
from src.twin.telemetry_simulator import DEFAULT_ROUTES


RISK_COLORS = {
    "normal": "#22c55e",
    "warning": "#f59e0b",
    "critical": "#ef4444",
    "unknown": "#94a3b8",
}
USER_MANUAL_PATH = Path(__file__).resolve().parents[1] / "docs" / "USER_MANUAL.md"


def get_store() -> TwinDemoStore:
    """Return the session-owned store without advancing it on rerun."""
    if "twin_store" not in st.session_state:
        st.session_state.twin_store = TwinDemoStore()
    return st.session_state.twin_store


def _risk_badge(status: str) -> str:
    return f"<span style='color:{RISK_COLORS.get(status, RISK_COLORS['unknown'])};font-weight:700'>{status.upper()}</span>"


def _fleet_frame(store: TwinDemoStore) -> pd.DataFrame:
    return pd.DataFrame(store.snapshot())


def render_overview(store: TwinDemoStore) -> None:
    st.title("REEFERTWIN Command Centre")
    st.caption("Live digital-twin projection for the Mumbai–Pune refrigerated corridor")
    frame = _fleet_frame(store)
    metrics = st.columns(4)
    metrics[0].metric("Vehicles", len(frame))
    metrics[1].metric("In transit", int((frame["status"] == "in_transit").sum()))
    metrics[2].metric("At risk", int(frame["risk"].isin(["warning", "critical"]).sum()))
    metrics[3].metric("Twin events", store.state_manager.event_count())
    render_alert_banner(frame)
    st.subheader("Fleet position")
    render_map(store)
    st.subheader("Fleet health")
    st.dataframe(
        frame[["vehicle_id", "temperature_c", "risk", "compressor", "destination", "updated_at"]],
        hide_index=True,
        use_container_width=True,
    )


def render_alert_banner(frame: pd.DataFrame) -> None:
    at_risk = frame[frame["risk"].isin(["warning", "critical"])]
    if at_risk.empty:
        st.success("All vehicles are within monitored operating limits.")
        return
    for row in at_risk.to_dict("records"):
        st.warning(
            f"{row['vehicle_id']} is {row['risk'].upper()}: "
            f"{row['temperature_c']:.2f}°C, compressor {row['compressor']}."
        )


def render_map(store: TwinDemoStore) -> None:
    frame = _fleet_frame(store)
    try:
        import pydeck as pdk

        frame["color"] = frame["risk"].map(RISK_COLORS)
        vehicle_layer = pdk.Layer(
            "ScatterplotLayer",
            data=frame,
            get_position="[longitude, latitude]",
            get_fill_color="color",
            get_radius=1800,
            pickable=True,
        )
        route_frame = pd.DataFrame(
            [
                {"path": [[longitude, latitude] for latitude, longitude in waypoints]}
                for waypoints in DEFAULT_ROUTES.values()
            ]
        )
        route_layer = pdk.Layer(
            "PathLayer",
            data=route_frame,
            get_path="path",
            get_color=[56, 189, 248],
            get_width=5,
            pickable=False,
        )
        st.pydeck_chart(
            pdk.Deck(
                layers=[route_layer, vehicle_layer],
                initial_view_state=pdk.ViewState(
                    latitude=18.8,
                    longitude=73.3,
                    zoom=8,
                    pitch=0,
                ),
                tooltip={"text": "{vehicle_id}\\n{risk} | {temperature_c}°C"},
            ),
            use_container_width=True,
        )
    except ImportError:
        st.info("PyDeck is unavailable; showing the route points in a table.")
        st.map(frame.rename(columns={"latitude": "lat", "longitude": "lon"})[
            ["lat", "lon"]
        ])


def render_digital_twin(store: TwinDemoStore) -> None:
    st.title("Digital Twin")
    st.caption("Select a vehicle to inspect projected state, telemetry, and evidence.")
    vehicle_id = st.selectbox("Vehicle", list(store.vehicles))
    vehicle = store.vehicles[vehicle_id]
    shipment = store.shipments[vehicle_id.replace("REEFER", "SHIPMENT")]
    risk = store.risk_for(vehicle_id)
    left, right = st.columns(2)
    with left:
        st.metric("Internal temperature", f"{risk.current_temperature_c:.2f} °C")
        st.metric("Compressor", vehicle.compressor_state.upper())
        st.metric("Position", f"{vehicle.latitude:.4f}, {vehicle.longitude:.4f}")
    with right:
        st.markdown(f"### Risk: {_risk_badge(risk.status)}", unsafe_allow_html=True)
        st.metric("Temperature deviation", f"{risk.temperature_deviation_c:.2f} °C")
        st.metric(
            "Estimated breach",
            "N/A"
            if risk.estimated_breach_minutes is None
            else f"{risk.estimated_breach_minutes:.0f} min",
        )
    st.markdown(f"**Shipment:** `{shipment.shipment_id}` · {shipment.cargo_category}")
    st.markdown(f"**Route:** {shipment.origin_name} → {shipment.destination_name}")
    st.subheader("Risk evidence")
    for evidence in risk.evidence:
        st.write(f"- {evidence}")
    st.caption(" | ".join(risk.limitations))
    history = pd.DataFrame(
        [
            {"observed_at": event.observed_at, "temperature_c": event.internal_temperature_c}
            for event in store.telemetry.get(vehicle_id, [])
        ]
    )
    if not history.empty:
        st.line_chart(history.set_index("observed_at"), y="temperature_c")


def render_fleet(store: TwinDemoStore) -> None:
    st.title("Fleet")
    frame = _fleet_frame(store)
    risk_filter = st.multiselect(
        "Risk state",
        ["normal", "warning", "critical", "unknown"],
        default=["normal", "warning", "critical", "unknown"],
    )
    filtered = frame[frame["risk"].isin(risk_filter)]
    st.dataframe(filtered, hide_index=True, use_container_width=True)
    render_map(store)


def render_simulation_lab(store: TwinDemoStore) -> None:
    st.title("Simulation Lab")
    st.caption("Controls mutate the scenario only after an explicit operator action.")
    st.write(f"Simulation clock: `{store.current_time.isoformat()}`")
    minutes = st.radio("Advance by", [1, 5, 15], horizontal=True)
    left, right = st.columns(2)
    with left:
        if st.button("Advance simulation", type="primary", use_container_width=True):
            store.advance(minutes)
            st.rerun()
    with right:
        if st.button("Reset deterministic scenario", use_container_width=True):
            store.reset()
            st.session_state.pop("what_if_scenario", None)
            st.session_state.pop("phase4_action_id", None)
            st.rerun()
    st.dataframe(
        _fleet_frame(store)[
            ["vehicle_id", "latitude", "longitude", "temperature_c", "risk", "updated_at"]
        ],
        hide_index=True,
        use_container_width=True,
    )


def render_what_if_lab(store: TwinDemoStore) -> None:
    st.title("What-if Simulation & Optimization")
    st.caption(
        "Disruptions are isolated from the baseline. Actions change only the "
        "scenario projection after approval."
    )
    manager = store.scenario_manager
    vehicle_id = st.selectbox(
        "Vehicle for new scenario",
        list(store.vehicles),
        key="what_if_vehicle",
    )
    disruption = st.selectbox(
        "Disruption",
        [item.value for item in ScenarioType],
        format_func=lambda value: value.replace("_", " ").title(),
    )
    warehouse_id = None
    if disruption in {
        ScenarioType.CAPACITY_REDUCTION.value,
        ScenarioType.WAREHOUSE_UNAVAILABLE.value,
    }:
        warehouse_id = st.selectbox(
            "Warehouse",
            list(store.warehouses),
            key="what_if_warehouse",
        )
    value = 0.0
    if disruption in {
        ScenarioType.HEATWAVE.value,
        ScenarioType.TEMPERATURE_SPIKE.value,
        ScenarioType.TRAFFIC_CONGESTION.value,
        ScenarioType.CAPACITY_REDUCTION.value,
    }:
        value = st.number_input(
            "Disruption value",
            min_value=0.0,
            value=2.0,
            help="Temperature delta, delay minutes, or capacity reduction depending on disruption.",
        )
    if st.button("Create isolated scenario", type="primary"):
        scenario = manager.simulate_disruption(
            disruption,
            vehicle_id=vehicle_id,
            warehouse_id=warehouse_id,
            value=value,
        )
        st.session_state["what_if_scenario"] = scenario.scenario_id
        st.rerun()

    if not manager.scenarios:
        st.info("Create a disruption to compare baseline and disrupted state.")
        return
    scenario_id = st.selectbox(
        "Scenario",
        list(manager.scenarios),
        format_func=lambda value: (
            f"{str(value)[:8]} ({manager.scenarios[value].vehicle_id})"
        ),
        key="what_if_scenario",
    )
    scenario = manager.scenarios[scenario_id]
    vehicle_id = scenario.vehicle_id
    st.info(f"Selected scenario vehicle: `{vehicle_id}`")
    comparison = manager.compare(scenario_id, vehicle_id)
    comparison_frame = pd.DataFrame(
        [
            {
                "metric": "Temperature (°C)",
                "baseline": comparison.baseline_temperature_c,
                "disrupted": comparison.disrupted_temperature_c,
            },
            {
                "metric": "Estimated breach (minutes)",
                "baseline": comparison.baseline_breach_minutes,
                "disrupted": comparison.disrupted_breach_minutes,
            },
            {
                "metric": "Risk",
                "baseline": comparison.baseline.status,
                "disrupted": comparison.disrupted.status,
            },
        ]
    )
    st.dataframe(comparison_frame, hide_index=True, use_container_width=True)
    ranking = manager.recommend(scenario_id, vehicle_id)
    st.subheader("Warehouse feasibility")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "warehouse_id": candidate.warehouse_id,
                    "feasible": candidate.feasible,
                    "arrival": candidate.arrival_at,
                    "safety_margin_min": candidate.safety_margin_minutes,
                    "cost": candidate.estimated_cost,
                    "rejections": ", ".join(candidate.rejection_reasons),
                }
                for candidate in ranking.candidates
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
    if ranking.selected_warehouse_id:
        st.success(f"Recommended destination: {ranking.selected_warehouse_id}")
        if st.button("Propose diversion action"):
            action = manager.propose_action(
                scenario_id, vehicle_id, ranking.selected_warehouse_id
            )
            st.session_state["phase4_action_id"] = action.action_id
            st.rerun()
    else:
        st.error("No feasible destination. Escalate to human logistics intervention.")
    action_id = st.session_state.get("phase4_action_id")
    if action_id and action_id in manager.actions:
        action = manager.actions[action_id]
        st.write(f"Action `{str(action.action_id)[:8]}` status: **{action.status}**")
        if action.status == ActionStatus.PROPOSED and st.button("Approve action"):
            manager.approve_action(action.action_id)
            st.rerun()
        if action.status == ActionStatus.APPROVED and st.button("Execute approved action"):
            manager.execute_action(action.action_id)
            st.success("Action executed in the scenario projection.")


def render_ai_command_centre(render_chat: Any) -> None:
    st.title("AI Command Centre")
    st.caption("Ask the existing LangGraph agent for evidence-backed operational analysis.")
    render_chat()


def render_audit(render_audit_logs: Any) -> None:
    st.title("Audit")
    st.caption("Decision traces and operator-visible execution records.")
    render_audit_logs()


def render_user_manual() -> None:
    """Display the repository's user manual inside the command centre."""
    st.title("REEFERTWIN User Manual")
    st.caption(
        "Setup, dashboard workflows, testing guidance, and verified limitations."
    )
    try:
        manual = USER_MANUAL_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        st.error(f"User manual could not be loaded: {exc}")
        return
    st.markdown(manual)
