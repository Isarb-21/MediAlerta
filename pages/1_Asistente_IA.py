import os

import streamlit as st
from dotenv import load_dotenv

import db
from agente_medialerta import preguntar_agente

load_dotenv()
st.set_page_config(page_title="MediAlerta | Asistente", page_icon="🤖", layout="wide")
db.init_db()
st.markdown('<p class="eyebrow">APOYO AL CUIDADOR</p>', unsafe_allow_html=True)
st.title("Asistente inteligente 🤖")
st.caption("Consulta registros demo de BPM, SpO₂, medicamentos e inventario.")
st.info("El asistente no diagnostica ni reemplaza a profesionales de salud. No recomienda cambiar medicamentos o dosis. Ante síntomas graves, contacta emergencias; no esperes al asistente.")
if not st.session_state.get("logged_in"):
    st.warning("Inicia sesión desde MediAlerta para continuar.")
    st.stop()
patient = db.get_patient()
summary = db.get_dashboard_summary(patient["id"])
context = {
    "modo_demo": True,
    "fuente": "Base de datos SQLite de demostración",
    "paciente": patient,
    "signos_vitales": {"bpm": summary["avg_bpm"], "spo2": summary["avg_spo2"], "fecha_registro": summary["date"]},
    "medicamentos": db.get_medication_logs(patient["id"]),
    "adherencia": {"porcentaje": summary["adherence"], "periodo": "hoy"},
    "inventario": db.get_inventory(patient["id"]),
    "alertas_registradas": {},
}
if "medialerta_chat" not in st.session_state:
    st.session_state["medialerta_chat"] = []
for message in st.session_state["medialerta_chat"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
question = st.chat_input("Pregunta por lecturas, dosis, inventario o alertas...")
if question:
    st.session_state["medialerta_chat"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Consultando registros..."):
            try:
                answer = preguntar_agente(question, datos_paciente=context, api_key=os.getenv("ANTHROPIC_API_KEY", ""))
            except Exception as error:
                answer = f"No se pudo consultar el asistente ({type(error).__name__})."
            st.markdown(answer)
    st.session_state["medialerta_chat"].append({"role": "assistant", "content": answer})
