import os

import streamlit as st
from dotenv import load_dotenv

from agente_medialerta import DataSourceError, obtener_datos_conectados, preguntar_agente

load_dotenv()

st.markdown('<p class="eyebrow">APOYO AL CUIDADOR</p>', unsafe_allow_html=True)
st.title("Asistente inteligente 🤖")
st.caption("Consulta BPM, SpO₂ y alertas registradas. La temperatura no se muestra porque no se mide.")
st.info("El agente no diagnostica ni reemplaza a profesionales de salud. Ante síntomas graves, contacta emergencias; no esperes al asistente.")

if not st.session_state.get("logged_in"):
    st.warning("Inicia sesión desde MediAlerta para continuar.")
    st.stop()

try:
    connected_data = obtener_datos_conectados()
except DataSourceError as error:
    st.error(f"No hay datos conectados: {error}")
    st.stop()

api_key = os.getenv("ANTHROPIC_API_KEY", "")
if "medialerta_chat" not in st.session_state:
    st.session_state["medialerta_chat"] = []

for message in st.session_state["medialerta_chat"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input("Pregunta por las lecturas o alertas disponibles...")
if question:
    st.session_state["medialerta_chat"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Revisando las fuentes conectadas..."):
            try:
                answer = preguntar_agente(question, datos_paciente=connected_data, api_key=api_key)
                st.markdown(answer)
            except Exception as error:
                answer = f"No se pudo consultar el agente ({type(error).__name__}). Comprueba la conexión y configuración."
                st.warning(answer)
    st.session_state["medialerta_chat"].append({"role": "assistant", "content": answer})
