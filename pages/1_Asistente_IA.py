from pathlib import Path

import os
import streamlit as st
from dotenv import load_dotenv
from anthropic import APIError

from agente_medialerta import DataSourceError, LIMITES_ALERTA, preguntar_agente

load_dotenv()
css_path = Path(__file__).resolve().parents[1] / "assets" / "styles.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

st.markdown('<p class="eyebrow">APOYO AL CUIDADOR</p>', unsafe_allow_html=True)
st.title("Asistente inteligente 🤖")
st.markdown('<p class="subtle">Consulta los datos registrados y recibe explicaciones claras y prudentes.</p>', unsafe_allow_html=True)
st.info(
    "El asistente no diagnostica ni reemplaza a profesionales de salud. "
    f"Las reglas de aviso configuradas son BPM <{LIMITES_ALERTA['bpm_minimo']} "
    f"o >{LIMITES_ALERTA['bpm_maximo']}, y oxigenación "
    f"<{LIMITES_ALERTA['spo2_minimo']}%; verifica estos límites con el "
    "equipo de salud. Ante síntomas graves, contacta emergencias sin "
    "esperar al agente."
)

if not st.session_state.get("logged_in"):
    st.warning("Inicia sesión desde la página principal de MediAlerta para usar el asistente.")
    st.stop()

aio_username = os.getenv("ADAFRUIT_IO_USERNAME", "").strip()
aio_key = os.getenv("ADAFRUIT_IO_KEY", "").strip()
api_key = os.getenv("ANTHROPIC_API_KEY") or st.session_state.get("anthropic_key", "")

if aio_username and aio_key:
    sheetdb_configured = bool(os.getenv("SHEETDB_API_URL", "").strip())
    st.info(
        "Modo conectado: el agente consulta las últimas lecturas de "
        "Adafruit IO y, si está configurado, la última alerta de pastillero "
        "en SheetDB. No se conecta directamente al ESP32 ni controla el "
        "motor. Telegram sigue gestionado por el firmware; el agente no "
        "envía avisos duplicados."
        + (
            ""
            if sheetdb_configured
            else " Configura SHEETDB_API_URL para consultar la alerta de pastillero."
        )
        + " Medicamentos y adherencia no están disponibles en esos feeds."
    )
elif aio_username or aio_key:
    st.warning(
        "La configuración de Adafruit IO está incompleta. Define "
        "ADAFRUIT_IO_USERNAME y ADAFRUIT_IO_KEY en el archivo .env."
    )
else:
    st.warning(
        "No hay una fuente conectada. Configura "
        "ADAFRUIT_IO_USERNAME y ADAFRUIT_IO_KEY en .env; el asistente no "
        "responderá usando datos de ejemplo."
    )

if "medialerta_chat" not in st.session_state:
    st.session_state["medialerta_chat"] = []

for message in st.session_state["medialerta_chat"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input("Ej.: ¿qué muestran las últimas lecturas?")
if question:
    st.session_state["medialerta_chat"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Revisando los registros disponibles..."):
            try:
                answer = preguntar_agente(question, api_key=api_key)
                st.markdown(answer)
            except DataSourceError as error:
                answer = (
                    "No pude consultar los datos conectados. "
                    f"{error} No tomaré decisiones con datos no verificados."
                )
                st.error(answer)
            except APIError as error:
                answer = (
                    "No pude contactar el servicio de Anthropic. Verifica la "
                    f"conexión y la clave ({type(error).__name__})."
                )
                st.error(answer)
    st.session_state["medialerta_chat"].append({"role": "assistant", "content": answer})

if not api_key:
    st.caption(
        "Sin ANTHROPIC_API_KEY, el agente responde con reglas locales. "
        "Sus respuestas usan únicamente los datos consultados de las "
        "fuentes conectadas."
    )
