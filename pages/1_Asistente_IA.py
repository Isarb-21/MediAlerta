import os

import streamlit as st
from dotenv import load_dotenv

from app import get_sample_data
from assistant_agent import ask_assistant

load_dotenv()

st.title("🤖 Asistente inteligente MediAlerta")
st.caption("Agente de apoyo para cuidadores. No sustituye a profesionales ni realiza diagnósticos.")

if not st.session_state.get("logged_in"):
    st.warning("Inicia sesión desde la página principal de MediAlerta para usar el asistente.")
    st.stop()

data = get_sample_data()
api_key = os.getenv("ANTHROPIC_API_KEY") or st.session_state.get("anthropic_key", "")

patient = data["patient"]
context = (
    f"Paciente: {patient['name']}, {patient['age']} años. Condición registrada: {patient['condition']}.\n"
    f"Signos vitales de ejemplo: BPM {data['vitals']['bpm']}, SpO₂ {data['vitals']['spo2']}%.\n"
    f"Adherencia semanal de ejemplo: {data['adherence']['semanal']}%.\n"
    f"Medicamentos y estados: {data['medications'][['medicamento', 'hora', 'dosis', 'estado']].to_dict(orient='records')}.\n"
    f"Alertas de ejemplo: {data['alerts']}.\n"
    "Todos los datos son simulados para una demostración y no representan mediciones clínicas reales."
)

if "medialerta_chat" not in st.session_state:
    st.session_state["medialerta_chat"] = []

for message in st.session_state["medialerta_chat"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input("Pregunta sobre alertas, adherencia o el estado registrado...")
if question:
    st.session_state["medialerta_chat"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        if not api_key:
            answer = (
                "El agente generativo requiere una clave de Anthropic. Configúrala en `.env` como "
                "`ANTHROPIC_API_KEY` y reinicia Streamlit. Por ahora, revisa las alertas mostradas "
                "en el dashboard y consulta al profesional de salud para decisiones sobre tratamiento."
            )
            st.info(answer)
        else:
            with st.spinner("El agente está revisando el contexto..."):
                try:
                    answer = ask_assistant(question, context, api_key)
                    st.markdown(answer)
                except Exception:
                    answer = (
                        "No pude contactar el servicio de IA. Verifica la conexión y la clave de API. "
                        "La información de esta demo no sustituye la orientación del profesional de salud."
                    )
                    st.warning(answer)

    st.session_state["medialerta_chat"].append({"role": "assistant", "content": answer})

if not api_key:
    st.caption("Configura ANTHROPIC_API_KEY para habilitar respuestas generativas. El dashboard funciona con datos simulados sin esa clave.")
