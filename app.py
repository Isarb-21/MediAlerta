"""MediAlerta caregiver dashboard: displays only connected sensor readings."""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from agente_medialerta import DataSourceError, obtener_datos_conectados, preguntar_agente

load_dotenv()

st.set_page_config(
    page_title="MediAlerta | Cuidado conectado",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def apply_styles():
    css_path = Path(__file__).parent / "assets" / "styles.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


apply_styles()


def login_view():
    left, right = st.columns([1.2, 1], gap="large", vertical_alignment="center")
    with left:
        logo = Path(__file__).parent / "assets" / "logo.svg"
        st.markdown(
            '<div class="login-hero"><p class="eyebrow">CUIDADO CONECTADO</p>'
            '<h1>MediAlerta</h1><p class="hero-copy">Signos vitales y alertas para acompañar a quienes cuidan.</p>'
            '<div class="hero-foot">Información clara para el cuidado diario</div></div>',
            unsafe_allow_html=True,
        )
        if logo.exists():
            st.image(str(logo), width=110)
    with right:
        st.markdown("### Bienvenido/a")
        st.caption("Acceso de demostración para cuidadores.")
        with st.form("login_form"):
            username = st.text_input("Usuario", placeholder="cuidador")
            password = st.text_input("Contraseña", type="password", placeholder="••••••")
            if st.form_submit_button("Ingresar a MediAlerta", use_container_width=True):
                if username.strip() and password.strip():
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = username.strip()
                    st.rerun()
                else:
                    st.warning("Ingresa usuario y contraseña para continuar.")
        st.caption("Demo: cualquier usuario y contraseña no vacíos.")


def load_connected_data():
    try:
        return obtener_datos_conectados(), None
    except DataSourceError as error:
        return None, str(error)


def render_dashboard(data, connection_error):
    st.markdown('<p class="eyebrow">LECTURAS DISPONIBLES</p>', unsafe_allow_html=True)
    st.title(f"Hola, {st.session_state.get('user', 'cuidador')} 👋")
    st.caption("MediAlerta muestra BPM y SpO₂; no mide ni reporta temperatura.")

    if connection_error:
        st.warning(f"No se pudieron cargar las lecturas: {connection_error}")
        st.info("Configura las credenciales de Adafruit IO en `.env`. La interfaz no inventa valores cuando falta una lectura.")
        return

    vitals = data.get("signos_vitales", {})
    bpm = vitals.get("bpm")
    spo2 = vitals.get("spo2")
    c1, c2, c3 = st.columns(3)
    c1.metric("❤️ Frecuencia cardiaca", f"{bpm} bpm" if bpm is not None else "Sin datos")
    c2.metric("🫁 Oxígeno en sangre", f"{spo2}%" if spo2 is not None else "Sin datos")
    c3.metric("🕒 Última lectura", vitals.get("fecha_registro") or "No disponible")

    st.markdown('<div class="demo-note">Datos recibidos de fuentes conectadas. Una lectura aislada no es un diagnóstico.</div>', unsafe_allow_html=True)
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("### Detalle de lecturas")
        st.write(f"**BPM:** {bpm if bpm is not None else 'Sin datos'} · {vitals.get('fecha_bpm') or 'sin fecha'}")
        spo2_text = f"{spo2}%" if spo2 is not None else "Sin datos"
        st.write(f"**SpO₂:** {spo2_text} · {vitals.get('fecha_spo2') or 'sin fecha'}")
        st.caption(f"Fuente: {data.get('fuente', 'No especificada')}")
    with right:
        st.markdown("### Alertas del pastillero")
        if data.get("registro_sheetdb_disponible"):
            st.write(f"**Estado registrado:** {data.get('alerta_pastillas_vacias') if data.get('alerta_pastillas_vacias') is not None else 'No interpretable'}")
            st.caption("Confirma físicamente el estado del pastillero.")
        else:
            st.info("No hay registro de pastillero conectado.")

    st.markdown("### Resumen del agente inteligente")
    if st.button("Analizar lecturas y alertas"):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        try:
            answer = preguntar_agente(
                "Resume las lecturas conectadas y las alertas disponibles.",
                datos_paciente=data,
                api_key=api_key,
            )
            st.session_state["dashboard_agent_summary"] = answer
        except Exception as error:
            st.warning(f"No se pudo completar el análisis: {type(error).__name__}.")
    if st.session_state.get("dashboard_agent_summary"):
        st.info(st.session_state["dashboard_agent_summary"])


def main():
    if not st.session_state.get("logged_in", False):
        login_view()
        return

    with st.sidebar:
        st.image("assets/logo.svg", width=145)
        st.caption(f"Sesión: {st.session_state.get('user', 'Cuidador')}")
        st.markdown("---")
        st.markdown("**Páginas**")
        st.page_link("app.py", label="Dashboard", icon="📊")
        st.page_link("pages/1_Asistente_IA.py", label="Asistente de cuidado", icon="🤖")
        st.page_link("pages/2_Carrito_de_compras.py", label="Carrito de compras", icon="🛒")
        st.markdown("---")
        with st.expander("⚙️ Configurar IA"):
            st.caption("Opcional: Claude activa las respuestas generativas. Sin clave, el agente usa reglas locales.")
            st.text_input("ANTHROPIC_API_KEY", type="password", key="anthropic_key", label_visibility="collapsed", placeholder="Clave API (opcional)")
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state.pop("user", None)
            st.rerun()
        st.markdown('<div class="sidebar-footer">MVP demostrativo · No sustituye orientación médica.</div>', unsafe_allow_html=True)

    data, error = load_connected_data()
    render_dashboard(data, error)


if __name__ == "__main__":
    main()
