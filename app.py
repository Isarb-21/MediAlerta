"""MediAlerta educational demo backed by a local SQLite database."""

import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import db
from agente_medialerta import preguntar_agente

load_dotenv()
st.set_page_config(page_title="MediAlerta | Cuidado conectado", page_icon="💊", layout="wide", initial_sidebar_state="expanded")


def apply_styles():
    css = Path(__file__).parent / "assets" / "styles.css"
    if css.exists():
        st.markdown(f"<style>{css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def login_view():
    left, right = st.columns([1.2, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown('<div class="login-hero"><p class="eyebrow">CUIDADO CONECTADO · DEMO EDUCATIVA</p><h1>MediAlerta</h1><p class="hero-copy">Signos vitales, medicamentos y reabastecimiento para acompañar a quienes cuidan.</p><div class="hero-foot">Los datos de esta demo se guardan en SQLite en tu equipo.</div></div>', unsafe_allow_html=True)
    with right:
        st.markdown("### Bienvenido/a")
        st.caption("Acceso de demostración: cualquier usuario y contraseña no vacíos.")
        with st.form("login_form"):
            username = st.text_input("Usuario", placeholder="cuidador")
            password = st.text_input("Contraseña", type="password", placeholder="••••••")
            if st.form_submit_button("Ingresar a MediAlerta", use_container_width=True):
                if username.strip() and password.strip():
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = username.strip()
                    st.rerun()
                st.warning("Ingresa usuario y contraseña para continuar.")


def display_time(value):
    if not value:
        return "No disponible"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return value


def render_dashboard(patient):
    st.markdown('<p class="eyebrow">RESUMEN DIARIO</p>', unsafe_allow_html=True)
    st.title(f"Hola, {st.session_state.get('user', 'cuidador')} 👋")
    st.caption("Métricas calculadas con los registros de hoy; solo BPM y SpO₂. No se mide temperatura.")
    summary = db.get_dashboard_summary(patient["id"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("❤️ BPM promedio del día", f"{summary['avg_bpm']} bpm" if summary["avg_bpm"] is not None else "Sin datos")
    c2.metric("🫁 SpO₂ promedio del día", f"{summary['avg_spo2']}%" if summary["avg_spo2"] is not None else "Sin datos")
    c3.metric("💊 Adherencia registrada hoy", f"{summary['adherence']}%")
    c4.metric("📡 Lecturas de hoy", str(summary["readings_count"]))
    st.caption(f"Periodo de los promedios: {date.today().strftime('%d/%m/%Y')} · Última lectura: {display_time(summary['latest'])}")
    st.markdown('<div class="demo-note">Prototipo educativo con datos simulados guardados localmente en SQLite. Las métricas no son una evaluación clínica.</div>', unsafe_allow_html=True)

    records = db.get_vitals(patient["id"], days=7)
    if records:
        frame = pd.DataFrame(records)
        frame["hora"] = pd.to_datetime(frame["recorded_at"]).dt.strftime("%d/%m %H:%M")
        st.markdown("### Tendencia de signos vitales · últimos 7 días")
        st.line_chart(frame.set_index("hora")[["bpm", "spo2"]])
    else:
        st.info("Aún no hay lecturas registradas.")

    with st.expander("Registrar lectura simulada"):
        with st.form("vital_form"):
            col1, col2 = st.columns(2)
            bpm = col1.number_input("BPM", min_value=1, max_value=300, value=76)
            spo2 = col2.number_input("SpO₂ (%)", min_value=0, max_value=100, value=98)
            if st.form_submit_button("Guardar lectura"):
                db.add_vital(patient["id"], bpm, spo2)
                st.success("Lectura guardada en SQLite.")
                st.rerun()

    alerts = db.build_demo_alerts(patient["id"])
    st.markdown("### Alertas generadas para revisar")
    if alerts:
        for alert in alerts:
            text = f"**{alert['type']} · {alert['severity']}** — {alert['message']}"
            st.error(text) if alert["severity"] == "Alta" else st.warning(text)
    else:
        st.success("No se generaron alertas por las reglas demo con los registros disponibles.")

    st.markdown("### Paciente")
    st.info(f"{patient['name']} · {patient['age']} años · Cuidador: {patient['caregiver_name']} · Contacto: {patient['phone']}")

    st.markdown("### Asistente inteligente")
    if st.button("Generar resumen de cuidado"):
        data = {
            "modo_demo": True,
            "fuente": "Base de datos SQLite de demostración",
            "paciente": patient,
            "signos_vitales": {"bpm": summary["avg_bpm"], "spo2": summary["avg_spo2"], "fecha_registro": summary["date"]},
            "medicamentos": db.get_medication_logs(patient["id"]),
            "adherencia": {"porcentaje": summary["adherence"], "periodo": "hoy"},
            "inventario": db.get_inventory(patient["id"]),
            "alertas_registradas": {},
        }
        try:
            answer = preguntar_agente("Resume el estado registrado hoy, las dosis y el inventario; indica acciones seguras.", datos_paciente=data, api_key=os.getenv("ANTHROPIC_API_KEY", ""))
            st.session_state["dashboard_agent_summary"] = answer
        except Exception as error:
            st.warning(f"No se pudo completar el análisis: {type(error).__name__}.")
    if st.session_state.get("dashboard_agent_summary"):
        st.info(st.session_state["dashboard_agent_summary"])


def main():
    apply_styles()
    db.init_db()
    if not st.session_state.get("logged_in", False):
        login_view()
        return
    patient = db.get_patient()
    with st.sidebar:
        logo = Path(__file__).parent / "assets" / "logo.svg"
        if logo.exists():
            st.image(str(logo), width=145)
        st.caption(f"Sesión demo: {st.session_state.get('user', 'Cuidador')}")
        st.caption("Datos locales persistentes · SQLite")
        st.markdown("---")
        st.page_link("app.py", label="Dashboard", icon="📊")
        st.page_link("pages/1_Asistente_IA.py", label="Asistente de cuidado", icon="🤖")
        st.page_link("pages/2_Carrito_de_compras.py", label="Carrito y pedidos", icon="🛒")
        st.page_link("pages/3_Medicamentos.py", label="Configurar medicamentos", icon="💊")
        st.markdown("---")
        with st.expander("⚙️ Configurar IA"):
            st.caption("Opcional: configura ANTHROPIC_API_KEY en .env para respuestas generativas. Sin clave, hay reglas locales.")
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state.pop("user", None)
            st.rerun()
        st.markdown('<div class="sidebar-footer">MVP educativo. No sustituye a profesionales de salud. Pagos y pedidos son simulados.</div>', unsafe_allow_html=True)
    render_dashboard(patient)


if __name__ == "__main__":
    main()
