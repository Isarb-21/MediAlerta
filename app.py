import os
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

st.set_page_config(
    page_title="MediAlerta",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)


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

    vitals = {
        "bpm": 76,
        "spo2": 98,
        "temperature": 36.7,
        "timestamp": "2026-11-08 08:45",
    }

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

    return {
        "patient": patient,
        "vitals": vitals,
        "medications": medications,
        "history": history,
        "alerts": alerts,
        "inventory": inventory,
        "vital_history": vital_history,
        "adherence": adherence,
    }


def get_ai_recommendation(data):
    api_key = os.getenv("ANTHROPIC_API_KEY") or st.session_state.get("anthropic_key")
    if not api_key:
        bpm = data["vitals"]["bpm"]
        spo2 = data["vitals"]["spo2"]
        if bpm > 85:
            return "El paciente presenta un valor de frecuencia cardiaca elevado. Se recomienda validar la toma de medicamentos y activar revisión del cuidador."
        if spo2 < 95:
            return "La frecuencia de oxígeno está por debajo del rango esperado. Se recomienda verificar estado respiratorio y avisar a la persona responsable."
        if data["medications"]["estado"].eq("Olvidado").any():
            return "Existe una dosis pendiente. Se recomienda recordar la administración y registrar la toma para mantener la adherencia."
        return "Estado general estable. La adherencia y los signos vitales se mantienen en rangos aceptables."

    try:
        llm = ChatAnthropic(model="claude-haiku-4-5-20251001", api_key=api_key, max_tokens=700)
        messages = [
            SystemMessage(content="Eres un asistente médico de apoyo para cuidadores y familiares. Responde en español, con tono claro, prioritario y clínicamente prudente. No reemplazas diagnósticos profesionales. Haz recomendaciones concisas y accionables para un paciente crónico."),
            HumanMessage(content=(
                f"Paciente: {data['patient']['name']} - {data['patient']['condition']}\n"
                f"BPM: {data['vitals']['bpm']}\nSpO2: {data['vitals']['spo2']}%\n"
                f"Adherencia semanal: {data['adherence']['semanal']}%\nAlertas: {len(data['alerts'])}\n"
                f"Medicamentos: {data['medications'].to_dict(orient='records')}\n"
                "Genera una recomendación breve para el cuidador con 3 puntos de acción y un resumen de riesgo."
            )),
        ]
        return llm.invoke(messages).content
    except Exception:
        return "La IA no pudo responder con la clave activa. Se muestra recomendación local basada en el estado actual del paciente."


def login_view():
    st.title("💊 MediAlerta")
    st.subheader("Sistema de monitoreo para cuidadores y familiares")
    with st.form("login_form"):
        st.markdown("### Iniciar sesión")
        username = st.text_input("Usuario", placeholder="cuidador")
        password = st.text_input("Contraseña", type="password", placeholder="••••••")
        login_btn = st.form_submit_button("Ingresar", use_container_width=True)
        if login_btn:
            if username.strip() and password.strip():
                st.session_state["logged_in"] = True
                st.session_state["user"] = username
                st.rerun()
            else:
                st.warning("Debes ingresar usuario y contraseña para continuar.")
    st.caption("Demo: usa cualquier usuario con contraseña válida para continuar.")


def render_dashboard(data):
    st.title("📊 Dashboard principal")
    patient, vitals, adherence = data["patient"], data["vitals"], data["adherence"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("❤️ BPM", f"{vitals['bpm']}", "Normal")
    col2.metric("🩸 SpO₂", f"{vitals['spo2']}%", "Estable")
    col3.metric("⏰ Próxima dosis", "20:00", "Hoy")
    col4.metric("📈 Adherencia", f"{adherence['semanal']}%", "Semanal")
    st.markdown("---")
    col_left, col_right = st.columns([1.8, 1.2])
    with col_left:
        st.subheader("Historial de signos vitales")
        st.line_chart(data["vital_history"].set_index("fecha")[["bpm", "spo2"]])
    with col_right:
        st.subheader("Estado del paciente")
        st.info(f"Paciente: {patient['name']}")
        st.info(f"Edad: {patient['age']} años")
        st.info(f"Condición: {patient['condition']}")
        st.info(f"Cuidador: {patient['caregiver']}")
    st.markdown("---")
    st.subheader("Recomendación del asistente")
    st.success(get_ai_recommendation(data))
    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Alertas recientes")
        for alert in data["alerts"]:
            severity = "🔴" if alert["prioridad"] == "Alta" else "🟠"
            st.markdown(f"{severity} **{alert['titulo']}**\n{alert['descripcion']}\nHora: {alert['hora']} | Tipo: {alert['tipo']}")
    with col_b:
        st.subheader("Medicamentos próximos")
        st.dataframe(data["medications"][["medicamento", "hora", "estado", "dosis"]], use_container_width=True, hide_index=True)


def render_medications(data):
    st.title("💊 Medicamentos")
    meds = data["medications"]
    st.dataframe(meds, use_container_width=True, hide_index=True)
    st.markdown("---")
    st.subheader("Estado de administración")
    for status, value in meds["estado"].value_counts().items():
        st.write(f"{status}: {value}")


def render_history(data):
    st.title("🧾 Historial")
    st.dataframe(data["history"], use_container_width=True, hide_index=True)
    st.markdown("---")
    st.subheader("Resumen semanal")
    st.progress(int(data["adherence"]["semanal"]))
    st.write(f"Adherencia semanal: {data['adherence']['semanal']}%")


def render_alerts(data):
    st.title("🚨 Alertas")
    for alert in data["alerts"]:
        message = f"**{alert['titulo']}**\n{alert['descripcion']}\nHora: {alert['hora']} | Tipo: {alert['tipo']}"
        st.error(message) if alert["prioridad"] == "Alta" else st.warning(message)


def render_inventory(data):
    st.title("📦 Inventario del pastillero")
    inventory = data["inventory"].copy()
    inventory["porcentaje"] = (inventory["stock"] / inventory["capacidad"]) * 100
    st.dataframe(inventory[["compartimento", "medicamento", "stock", "capacidad", "estado"]], use_container_width=True, hide_index=True)
    st.markdown("---")
    for _, item in inventory.iterrows():
        st.write(f"{item['compartimento']} - {item['medicamento']}")
        st.progress(min(item["porcentaje"], 100) / 100)
        st.caption(f"{item['stock']} / {item['capacidad']} unidades")


def render_profile(data):
    st.title("👤 Perfil y contactos")
    patient = data["patient"]
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Nombre:** {patient['name']}")
        st.markdown(f"**Edad:** {patient['age']} años")
        st.markdown(f"**Condición:** {patient['condition']}")
    with col2:
        st.markdown(f"**Cuidador:** {patient['caregiver']}")
        st.markdown(f"**Teléfono:** {patient['phone']}")
        st.markdown(f"**Contacto de emergencia:** {patient['emergency_contact']}")


def main():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if not st.session_state["logged_in"]:
        login_view()
        return

    data = get_sample_data()
    with st.sidebar:
        st.title("MediAlerta")
        st.caption(f"Bienvenido/a, {st.session_state.get('user', 'Cuidador')}")
        st.markdown("---")
        page = st.radio("Navegación", ["Dashboard", "Medicamentos", "Historial", "Alertas", "Inventario", "Perfil"], index=0)
        st.markdown("---")
        st.text_input("API Key Anthropic (opcional)", type="password", key="anthropic_key")
        if st.button("Cerrar sesión"):
            st.session_state["logged_in"] = False
            st.session_state.pop("user", None)
            st.rerun()

    pages = {
        "Dashboard": render_dashboard,
        "Medicamentos": render_medications,
        "Historial": render_history,
        "Alertas": render_alerts,
        "Inventario": render_inventory,
        "Perfil": render_profile,
    }
    pages[page](data)


if __name__ == "__main__":
    main()
