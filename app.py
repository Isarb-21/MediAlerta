import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

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


@st.cache_data
def get_sample_data():
    patient = {
        "name": "Ana García",
        "age": 72,
        "condition": "Hipertensión y diabetes tipo 2",
        "caregiver": "María López",
        "phone": "+57 311 234 5678",
        "emergency_contact": "Camilo García",
    }

    vitals = {"bpm": 76, "spo2": 98, "temperature": 36.7, "timestamp": "2026-11-08 08:45"}

    medications = pd.DataFrame(
        [
            {"medicamento": "Losartán", "hora": "08:00", "dosis": "50 mg", "estado": "Tomado", "compartimento": "A1", "proxima_dosis": "Hoy 20:00"},
            {"medicamento": "Metformina", "hora": "08:30", "dosis": "500 mg", "estado": "Tomado", "compartimento": "B2", "proxima_dosis": "Mañana 08:30"},
            {"medicamento": "Atorvastatina", "hora": "20:00", "dosis": "20 mg", "estado": "Pendiente", "compartimento": "C1", "proxima_dosis": "Hoy 20:00"},
            {"medicamento": "Vitamina D", "hora": "21:00", "dosis": "1 cápsula", "estado": "Olvidado", "compartimento": "D3", "proxima_dosis": "Hoy 21:00"},
        ]
    )

    history = pd.DataFrame(
        [
            {"fecha": "01/11", "medicamento": "Losartán", "estado": "✅ Tomado"},
            {"fecha": "02/11", "medicamento": "Metformina", "estado": "✅ Tomado"},
            {"fecha": "03/11", "medicamento": "Atorvastatina", "estado": "⚠️ Olvidado"},
            {"fecha": "04/11", "medicamento": "Vitamina D", "estado": "✅ Tomado"},
            {"fecha": "05/11", "medicamento": "Losartán", "estado": "✅ Tomado"},
            {"fecha": "06/11", "medicamento": "Metformina", "estado": "⚠️ Retraso"},
        ]
    )

    alerts = [
        {"tipo": "Biomédica", "titulo": "BPM alto", "descripcion": "El paciente presenta 92 bpm, por encima del rango normal.", "hora": "08:35", "prioridad": "Alta"},
        {"tipo": "Medicación", "titulo": "Dosis olvidada", "descripcion": "La dosis de Atorvastatina no fue retirada a la hora indicada.", "hora": "20:15", "prioridad": "Media"},
        {"tipo": "Inventario", "titulo": "Pastillero casi vacío", "descripcion": "Falta disponibilidad de 2 compartimentos del pastillero.", "hora": "07:50", "prioridad": "Media"},
    ]

    inventory = pd.DataFrame(
        [
            {"compartimento": "A1", "medicamento": "Losartán", "stock": 12, "capacidad": 14, "estado": "OK"},
            {"compartimento": "B2", "medicamento": "Metformina", "stock": 9, "capacidad": 10, "estado": "OK"},
            {"compartimento": "C1", "medicamento": "Atorvastatina", "stock": 2, "capacidad": 7, "estado": "Bajo"},
            {"compartimento": "D3", "medicamento": "Vitamina D", "stock": 0, "capacidad": 5, "estado": "Vacío"},
        ]
    )

    vital_history = pd.DataFrame(
        [
            {"fecha": "01/11", "bpm": 74, "spo2": 97},
            {"fecha": "02/11", "bpm": 72, "spo2": 98},
            {"fecha": "03/11", "bpm": 82, "spo2": 96},
            {"fecha": "04/11", "bpm": 76, "spo2": 99},
            {"fecha": "05/11", "bpm": 79, "spo2": 98},
            {"fecha": "06/11", "bpm": 77, "spo2": 97},
            {"fecha": "07/11", "bpm": 76, "spo2": 98},
        ]
    )

    adherence = {"semanal": 90, "mensual": 89, "ultima_semana": 6, "tomadas": 18, "faltantes": 2}
    return {"patient": patient, "vitals": vitals, "medications": medications, "history": history, "alerts": alerts, "inventory": inventory, "vital_history": vital_history, "adherence": adherence}


def get_ai_recommendation(data):
    api_key = os.getenv("ANTHROPIC_API_KEY") or st.session_state.get("anthropic_key")
    if not api_key:
        bpm, spo2 = data["vitals"]["bpm"], data["vitals"]["spo2"]
        if bpm > 85:
            return "El valor de frecuencia cardiaca de ejemplo está elevado. Verifica que la medición se haya realizado correctamente y contacta al profesional responsable si persiste o preocupa."
        if spo2 < 95:
            return "La lectura de oxígeno de ejemplo está por debajo del umbral de demostración. Verifica la medición y consulta al profesional responsable."
        if data["medications"]["estado"].eq("Olvidado").any():
            return "Hay una dosis marcada como olvidada en los datos de demostración. Confirma el registro con el cuidador y consulta al profesional si tienes dudas sobre qué hacer."
        return "Los valores de ejemplo están dentro de los umbrales de esta demostración. Confirma siempre cualquier lectura con el dispositivo y sigue las indicaciones del equipo de salud."

    try:
        llm = ChatAnthropic(model="claude-haiku-4-5-20251001", api_key=api_key, max_tokens=700)
        messages = [
            SystemMessage(content="Eres un asistente informativo para cuidadores. Responde en español, de forma prudente y clara. No diagnostiques ni indiques iniciar, suspender o cambiar medicamentos. Estos datos son simulados. Si describen síntomas graves o empeoramiento repentino, recomienda contactar inmediatamente los servicios de emergencia locales y al profesional de salud. No sustituyes atención profesional."),
            HumanMessage(content=(
                f"Paciente de demostración: {data['patient']['name']} - {data['patient']['condition']}\n"
                f"BPM: {data['vitals']['bpm']}\nSpO₂: {data['vitals']['spo2']}%\n"
                f"Adherencia semanal: {data['adherence']['semanal']}%\nAlertas: {data['alerts']}\n"
                f"Medicamentos: {data['medications'].to_dict(orient='records')}\n"
                "Resume la situación y sugiere acciones seguras para el cuidador. Aclara que no es un diagnóstico."
            )),
        ]
        return llm.invoke(messages).content
    except Exception:
        return "No fue posible consultar la IA. Revisa la clave/conexión y consulta al profesional de salud para decisiones clínicas."


def login_view():
    left, right = st.columns([1.2, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(
            '<div class="login-hero"><img src="https://raw.githubusercontent.com/Isarb-21/MediAlerta/main/assets/logo.svg" class="hero-logo" alt="MediAlerta logo" /><p class="eyebrow">CUIDADO CONECTADO</p><h1>Más tranquilidad<br>para quienes cuidan.</h1><p class="hero-copy">Signos vitales, medicamentos y alertas importantes en un solo lugar.</p><div class="hero-foot">MediAlerta <span>•</span> Demo de acompañamiento</div></div>',
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
    patient, vitals, adherence = data["patient"], data["vitals"], data["adherence"]
    st.markdown('<p class="eyebrow">VISTA GENERAL · HOY</p>', unsafe_allow_html=True)
    st.title(f"Buenos días, {st.session_state.get('user', 'cuidador')} 👋")
    st.markdown(f'<p class="subtle">Aquí tienes el resumen de cuidado de <b>{patient["name"]}</b>.</p>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("❤️  Frecuencia cardiaca", f"{vitals['bpm']} bpm", "En rango demo")
    c2.metric("🫁  Oxígeno en sangre", f"{vitals['spo2']}%", "Estable · demo")
    c3.metric("⏰  Próxima dosis", "20:00", "Atorvastatina")
    c4.metric("📈  Adherencia semanal", f"{adherence['semanal']}%", "+4% vs. semana anterior")

    st.markdown('<div class="demo-note">● Datos de demostración — no corresponden a mediciones clínicas en tiempo real.</div>', unsafe_allow_html=True)
    st.markdown("")
    left, right = st.columns([1.65, 1], gap="large")
    with left:
        st.markdown('<div class="section-heading"><div><p class="eyebrow">TENDENCIA</p><h3>Signos vitales</h3></div><span class="tag">Últimos 7 días</span></div>', unsafe_allow_html=True)
        st.line_chart(data["vital_history"].set_index("fecha")[["bpm", "spo2"]], height=260)
    with right:
        st.markdown('<p class="eyebrow">PACIENTE</p><h3>Resumen de cuidado</h3>', unsafe_allow_html=True)
        st.markdown(f'<div class="patient-card"><div class="avatar">{patient["name"][0]}</div><div><b>{patient["name"]}</b><br><span>{patient["age"]} años · {patient["condition"]}</span></div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="detail-row"><span>Cuidador principal</span><b>{patient["caregiver"]}</b></div><div class="detail-row"><span>Última actualización</span><b>{vitals["timestamp"]}</b></div>', unsafe_allow_html=True)
        st.progress(adherence["semanal"] / 100, text=f"Adherencia semanal · {adherence['semanal']}%")

    st.markdown('<p class="eyebrow section-eyebrow">PARA TENER EN CUENTA</p>', unsafe_allow_html=True)
    alerts_col, meds_col = st.columns(2, gap="large")
    with alerts_col:
        st.markdown("### Alertas recientes")
        for alert in data["alerts"][:2]:
            st.markdown(f'<div class="alert-card {"alert-high" if alert["prioridad"] == "Alta" else "alert-medium"}"><div><b>{alert["titulo"]}</b><br><span>{alert["descripcion"]}</span></div><small>{alert["hora"]}</small></div>', unsafe_allow_html=True)
    with meds_col:
        st.markdown("### Próximos medicamentos")
        st.dataframe(data["medications"][["medicamento", "hora", "estado"]], use_container_width=True, hide_index=True)

    st.markdown("### Recomendación del asistente")
    st.info(get_ai_recommendation(data))


def render_medications(data):
    st.markdown('<p class="eyebrow">TRATAMIENTO</p>', unsafe_allow_html=True)
    st.title("Medicamentos")
    st.markdown('<p class="subtle">Consulta el horario y el estado de cada dosis registrada.</p>', unsafe_allow_html=True)
    st.dataframe(data["medications"], use_container_width=True, hide_index=True)
    counts = data["medications"]["estado"].value_counts()
    cols = st.columns(max(len(counts), 1))
    for col, (status, count) in zip(cols, counts.items()):
        col.metric(status, count)


def render_history(data):
    st.markdown('<p class="eyebrow">SEGUIMIENTO</p>', unsafe_allow_html=True)
    st.title("Historial de medicación")
    st.markdown('<p class="subtle">Revisa las dosis registradas y la adherencia.</p>', unsafe_allow_html=True)
    st.dataframe(data["history"], use_container_width=True, hide_index=True)
    st.markdown("### Adherencia semanal")
    st.progress(int(data["adherence"]["semanal"]), text=f"{data['adherence']['semanal']}% de adherencia · datos de demostración")


def render_alerts(data):
    st.markdown('<p class="eyebrow">CENTRO DE NOTIFICACIONES</p>', unsafe_allow_html=True)
    st.title("Alertas")
    st.markdown('<p class="subtle">Avisos simulados para apoyar el seguimiento del cuidador.</p>', unsafe_allow_html=True)
    for alert in data["alerts"]:
        message = f"**{alert['titulo']}**  \n{alert['descripcion']}  \n`{alert['tipo']} · {alert['hora']} · Prioridad {alert['prioridad']}`"
        st.error(message) if alert["prioridad"] == "Alta" else st.warning(message)


def render_inventory(data):
    st.markdown('<p class="eyebrow">PASTILLERO</p>', unsafe_allow_html=True)
    st.title("Inventario")
    st.markdown('<p class="subtle">Existencias registradas por compartimento.</p>', unsafe_allow_html=True)
    inventory = data["inventory"].copy()
    inventory["porcentaje"] = (inventory["stock"] / inventory["capacidad"]) * 100
    st.dataframe(inventory[["compartimento", "medicamento", "stock", "capacidad", "estado"]], use_container_width=True, hide_index=True)
    cols = st.columns(2)
    for index, (_, item) in enumerate(inventory.iterrows()):
        with cols[index % 2]:
            st.markdown(f"**{item['compartimento']} · {item['medicamento']}** — {item['estado']}")
            st.progress(min(item["porcentaje"], 100) / 100, text=f"{item['stock']} de {item['capacidad']} unidades")


def render_profile(data):
    st.markdown('<p class="eyebrow">CUENTA Y CONTACTOS</p>', unsafe_allow_html=True)
    st.title("Perfil del paciente")
    patient = data["patient"]
    left, right = st.columns(2)
    with left:
        st.markdown("### Información personal")
        st.write(f"**Nombre:** {patient['name']}")
        st.write(f"**Edad:** {patient['age']} años")
        st.write(f"**Condición registrada:** {patient['condition']}")
    with right:
        st.markdown("### Red de apoyo")
        st.write(f"**Cuidador:** {patient['caregiver']}")
        st.write(f"**Teléfono:** {patient['phone']}")
        st.write(f"**Contacto de emergencia:** {patient['emergency_contact']}")


def main():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if not st.session_state["logged_in"]:
        login_view()
        return

    data = get_sample_data()
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

    pages = {"Dashboard": render_dashboard, "Medicamentos": render_medications, "Historial": render_history, "Alertas": render_alerts, "Inventario": render_inventory, "Perfil": render_profile}
    pages[page](data)


if __name__ == "__main__":
    main()
