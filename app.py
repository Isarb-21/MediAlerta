"""Aplicación Streamlit de demostración para el seguimiento de cuidados."""

# ---------------------------------------------------------------------------
# Configuración general y estilos
# ---------------------------------------------------------------------------
import base64
import os
from pathlib import Path

import streamlit as st
from anthropic import APIError
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
    """Carga los estilos de la aplicación desde assets/styles.css, si existe."""
    css_path = Path(__file__).parent / "assets" / "styles.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


apply_styles()


# ---------------------------------------------------------------------------
# Datos conectados y recomendaciones
# ---------------------------------------------------------------------------
def get_connected_data():
    """Obtiene únicamente los registros disponibles en Adafruit IO y SheetDB."""
    connected = obtener_datos_conectados()
    vitals = connected["signos_vitales"]
    alerts = [
        {"campo": name, "valor": value}
        for name, value in connected.get("alertas_registradas", {}).items()
        if value is not None
    ]
    return {
        "patient": {},
        "vitals": {
            "bpm": vitals.get("bpm"),
            "spo2": vitals.get("spo2"),
            "temperature": vitals.get("temperatura"),
            "timestamp": vitals.get("fecha_registro"),
        },
        "source": connected["fuente"],
        "agent_data": connected,
        "alerts": alerts,
        "medications": [],
        "history": [],
        "inventory": [],
        "adherence": None,
    }


def get_empty_connected_data(error):
    """Prepara la estructura de las vistas cuando no se pueden leer datos."""
    return {
        "patient": {},
        "vitals": {
            "bpm": None,
            "spo2": None,
            "temperature": None,
            "timestamp": None,
            "fecha_bpm": None,
            "fecha_spo2": None,
        },
        "source": "Adafruit IO",
        "agent_data": {},
        "alerts": [],
        "medications": [],
        "history": [],
        "inventory": [],
        "adherence": None,
        "connection_error": str(error),
    }


def get_ai_recommendation(data):
    """Resume solo los datos que entregan las fuentes conectadas."""
    api_key = os.getenv("ANTHROPIC_API_KEY") or st.session_state.get("anthropic_key", "")
    return preguntar_agente(
        "Dame un resumen de las últimas lecturas y alertas registradas.",
        datos_paciente=data["agent_data"],
        api_key=api_key,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Vistas de la aplicación
# ---------------------------------------------------------------------------
def login_view():
    """Muestra el formulario de acceso y la presentación de MediAlerta."""
    logo_path = Path(__file__).parent / "assets" / "logo.svg"
    logo_data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    left, right = st.columns([1.2, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(
            f'<div class="login-hero"><img src="data:image/svg+xml;base64,{logo_data}" class="hero-logo" alt="MediAlerta logo" /><p class="eyebrow">CUIDADO CONECTADO</p><h1>Más tranquilidad<br>para quienes cuidan.</h1><p class="hero-copy">Signos vitales, medicamentos y alertas importantes en un solo lugar.</p><div class="hero-foot">MediAlerta <span>•</span> Demo de acompañamiento</div></div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.markdown("### Bienvenido/a", help="Acceso de demostración")
        st.caption("Ingresa para revisar el estado de tu paciente.")
        with st.form("login_form"):
            username = st.text_input("Usuario", placeholder="cuidador")
            password = st.text_input("Contraseña", type="password", placeholder="••••••")
            if st.form_submit_button("Ingresar a MediAlerta", use_container_width=True):
                if username.strip() and password.strip():
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = username
                    st.rerun()
                else:
                    st.warning("Ingresa usuario y contraseña para continuar.")
        st.caption("Demo: cualquier usuario y contraseña no vacíos.")
        st.markdown("</div>", unsafe_allow_html=True)


def render_dashboard(data):
    """Muestra las últimas lecturas y los registros recibidos de las fuentes."""
    vitals = data["vitals"]
    st.markdown('<p class="eyebrow">LECTURAS CONECTADAS</p>', unsafe_allow_html=True)
    st.title(f"Buenos días, {st.session_state.get('user', 'cuidador')} 👋")
    st.caption(f"Fuente: {data['source']}. Solo se muestran datos recibidos.")

    c1, c2, c3, c4 = st.columns(4)
    bpm = f"{vitals['bpm']} bpm" if vitals["bpm"] is not None else "Sin datos"
    spo2 = f"{vitals['spo2']}%" if vitals["spo2"] is not None else "Sin datos"
    c1.metric("❤️  Frecuencia cardiaca", bpm)
    c2.metric("🫁  Oxígeno en sangre", spo2)
    temperature = vitals["temperature"]
    c3.metric(
        "🌡️  Temperatura",
        f"{temperature} °C" if temperature is not None else "No disponible",
    )
    c4.metric("🕒  Última lectura", vitals["timestamp"] or "No disponible")

    left, right = st.columns([1.65, 1], gap="large")
    with left:
        st.markdown("### Lecturas recibidas")
        st.write(f"**BPM:** {vitals['bpm'] if vitals['bpm'] is not None else 'Sin datos'} · Registro: {vitals.get('fecha_bpm') or 'sin fecha'}")
        spo2_reading = f"{vitals['spo2']}%" if vitals["spo2"] is not None else "Sin datos"
        st.write(f"**Oxigenación:** {spo2_reading} · Registro: {vitals.get('fecha_spo2') or 'sin fecha'}")
        st.info("El feed disponible entrega la última lectura, no un historial de varios días.")
    with right:
        st.markdown("### Información del paciente")
        st.info("No hay datos personales ni adherencia disponibles en las fuentes conectadas.")

    alerts_col, meds_col = st.columns(2, gap="large")
    with alerts_col:
        st.markdown("### Campos de alerta recibidos")
        if data["alerts"]:
            for alert in data["alerts"]:
                st.write(f"**{alert['campo']}:** {alert['valor']}")
            st.caption("Se muestran los valores registrados sin interpretarlos.")
        else:
            st.info("No hay campos de alerta disponibles.")
    with meds_col:
        st.markdown("### Medicamentos")
        st.info("Las fuentes conectadas no proporcionan horarios ni registros de dosis.")

    st.markdown("### Recomendación del asistente")
    if data.get("connection_error"):
        st.info("Cuando el dispositivo envíe sus primeras lecturas, aparecerán aquí. Mientras tanto, puedes explorar las secciones disponibles.")
    else:
        try:
            st.info(get_ai_recommendation(data))
        except APIError as error:
            st.error(f"No pude generar el resumen ({type(error).__name__}).")


def render_medications(data):
    """Muestra los datos de medicación si alguna fuente los proporciona."""
    st.markdown('<p class="eyebrow">TRATAMIENTO</p>', unsafe_allow_html=True)
    st.title("Medicamentos")
    st.info("No hay horarios ni registros de medicamentos en las fuentes conectadas.")


def render_history(data):
    """Muestra el historial de medicación disponible."""
    st.markdown('<p class="eyebrow">SEGUIMIENTO</p>', unsafe_allow_html=True)
    st.title("Historial de medicación")
    st.info("No hay historial de dosis ni datos de adherencia en las fuentes conectadas.")


def render_alerts(data):
    """Presenta los valores de alerta recibidos, sin inferir su significado."""
    st.markdown('<p class="eyebrow">CENTRO DE NOTIFICACIONES</p>', unsafe_allow_html=True)
    st.title("Alertas")
    if not data["alerts"]:
        st.info("No hay campos de alerta disponibles en las fuentes conectadas.")
        return
    for alert in data["alerts"]:
        st.write(f"**{alert['campo']}:** {alert['valor']}")
    st.caption("Confirma el significado de estos campos con la configuración del dispositivo.")


def render_inventory(data):
    """Muestra el inventario si existe información real conectada."""
    st.markdown('<p class="eyebrow">PASTILLERO</p>', unsafe_allow_html=True)
    st.title("Inventario")
    st.info("No hay cantidades por compartimento disponibles en las fuentes conectadas.")


def render_profile(data):
    """Muestra la información personal disponible."""
    st.markdown('<p class="eyebrow">CUENTA Y CONTACTOS</p>', unsafe_allow_html=True)
    st.title("Perfil del paciente")
    st.info("Las fuentes conectadas no proporcionan datos personales ni contactos.")


# ---------------------------------------------------------------------------
# Navegación, sesión y punto de entrada
# ---------------------------------------------------------------------------
def main():
    """Controla el acceso, la barra lateral y el enrutamiento entre vistas."""
    # Inicializa el acceso y detiene el flujo para mostrar el login si es necesario.
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if not st.session_state["logged_in"]:
        login_view()
        return

    try:
        data = get_connected_data()
    except DataSourceError as error:
        data = get_empty_connected_data(error)

    # La barra lateral contiene identidad, navegación, configuración de IA y salida.
    with st.sidebar:
        st.image("assets/logo.svg", width=170)
        st.markdown(f'<div class="user-chip">👋 &nbsp; {st.session_state.get("user", "Cuidador")}</div>', unsafe_allow_html=True)
        st.markdown('<p class="nav-label">MENÚ PRINCIPAL</p>', unsafe_allow_html=True)
        page = st.radio("Navegación", ["Dashboard", "Medicamentos", "Historial", "Alertas", "Inventario", "Perfil"], label_visibility="collapsed", index=0)
        st.markdown("---")
        with st.expander("⚙️ Configurar IA"):
            st.caption("Opcional: habilita recomendaciones de Claude.")
            st.text_input("API Key Anthropic", type="password", key="anthropic_key", label_visibility="collapsed", placeholder="ANTHROPIC_API_KEY")
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state.pop("user", None)
            st.rerun()
        st.markdown('<div class="sidebar-footer">MVP demostrativo<br>La información no sustituye consejo médico.</div>', unsafe_allow_html=True)

    # Asocia cada opción del menú con su función de renderizado y muestra la vista.
    pages = {"Dashboard": render_dashboard, "Medicamentos": render_medications, "Historial": render_history, "Alertas": render_alerts, "Inventario": render_inventory, "Perfil": render_profile}
    if data.get("connection_error"):
        st.warning(f"No pude cargar las lecturas conectadas: {data['connection_error']}")
    pages[page](data)


if __name__ == "__main__":
    main()
