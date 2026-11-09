from pathlib import Path

import os
import streamlit as st
from dotenv import load_dotenv

from app import get_sample_data
from assistant_agent import ask_assistant

load_dotenv()
css_path = Path(__file__).resolve().parents[1] / "assets" / "styles.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

st.markdown('<p class="eyebrow">APOYO AL CUIDADOR</p>', unsafe_allow_html=True)
st.title("Asistente inteligente 🤖")
st.markdown('<p class="subtle">Consulta los datos registrados y recibe explicaciones claras y prudentes.</p>', unsafe_allow_html=True)
st.info("El asistente no diagnostica ni reemplaza a profesionales de salud. Los datos de esta demo son simulados.")

if not st.session_state.get("logged_in"):
    st.warning("Inicia sesión desde la página principal de MediAlerta para usar el asistente.")
    st.stop()

data = get_sample_data()
api_key = os.getenv("ANTHROPIC_API_KEY") or st.session_state.get("anthropic_key", "")
patient = data["patient"]
context = (
    f"Paciente: {patient['name']}, {patient['age']} años. Condición registrada: {patient['condition']}.\n"
    f"Signos vitales simulados: BPM {data['vitals']['bpm']}, SpO₂ {data['vitals']['spo2']}%.\n"
    f"Adherencia semanal simulada: {data['adherence']['semanal']}%.\n"
    f"Medicamentos y estados: {data['medications'][['medicamento', 'hora', 'dosis', 'estado']].to_dict(orient='records')}.\n"
    f"Alertas simuladas: {data['alerts']}.\n"
    "Los datos no representan mediciones clínicas reales."
)

if "medialerta_chat" not in st.session_state:
    st.session_state["medialerta_chat"] = []

for message in st.session_state["medialerta_chat"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input("Ej.: ¿qué dosis aparece pendiente?")
if question:
    st.session_state["medialerta_chat"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        if not api_key:
            answer = "Para habilitar respuestas generativas, configura `ANTHROPIC_API_KEY` en `.env`. Mientras tanto, revisa las alertas del dashboard y consulta al profesional de salud para decisiones sobre tratamiento."
            st.info(answer)
        else:
            with st.spinner("Revisando el contexto de demostración..."):
                try:
                    answer = ask_assistant(question, context, api_key)
                    st.markdown(answer)
                except Exception:
                    answer = "No pude contactar el servicio de IA. Verifica tu clave y conexión. Esta demo no sustituye la orientación profesional."
                    st.warning(answer)
    st.session_state["medialerta_chat"].append({"role": "assistant", "content": answer})

if not api_key:
    st.caption("La función de chat requiere una clave Anthropic. El resto del prototipo puede usarse sin ella.")
