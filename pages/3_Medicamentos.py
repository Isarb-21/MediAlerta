"""Medication schedule and pillbox inventory configuration for the demo."""

from datetime import datetime

import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="MediAlerta | Medicamentos", page_icon="💊", layout="wide")
db.init_db()
if not st.session_state.get("logged_in"):
    st.warning("Inicia sesión desde MediAlerta para continuar.")
    st.stop()
patient = db.get_patient()
st.markdown('<p class="eyebrow">TRATAMIENTO E INVENTARIO</p>', unsafe_allow_html=True)
st.title("Configurar medicamentos 💊")
st.caption("Los horarios se guardan y muestran en formato de 24 horas. Esta demo no prescribe ni modifica tratamientos.")
medications = db.list_medications(patient["id"])

with st.expander("➕ Agregar medicamento al plan configurado", expanded=not medications):
    with st.form("new_medication"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Nombre del medicamento")
        dose = c2.text_input("Dosis tal como fue indicada por el profesional")
        c3, c4, c5 = st.columns(3)
        scheduled = c3.time_input("Hora programada", value=datetime.strptime("08:00", "%H:%M").time(), step=300, help="Formato 24 horas")
        compartment = c4.text_input("Compartimento", placeholder="A1")
        stock = c5.number_input("Unidades disponibles", min_value=0, value=0, step=1)
        c6, c7 = st.columns(2)
        minimum = c6.number_input("Mínimo para alerta/reposición", min_value=0, value=2, step=1)
        price = c7.number_input("Precio unitario demo (COP)", min_value=0, value=10000, step=500)
        if st.form_submit_button("Guardar medicamento", type="primary"):
            try:
                db.save_medication(patient["id"], name, dose, scheduled.strftime("%H:%M"), compartment, int(stock), int(minimum), float(price))
                st.success("Medicamento e inventario guardados en SQLite.")
                st.rerun()
            except (ValueError, Exception) as error:
                st.error(f"No se pudo guardar: {error}")

medications = db.list_medications(patient["id"])
st.subheader("Medicamentos configurados")
if medications:
    df = pd.DataFrame([{"Medicamento": m["name"], "Dosis": m["dose"], "Hora (24 h)": m["scheduled_time"], "Compartimento": m["compartment"], "Stock": m["stock"], "Mínimo": m["min_stock"], "Precio demo (COP)": m["unit_price"]} for m in medications])
    st.dataframe(df, use_container_width=True, hide_index=True)
    with st.expander("Editar programación o inventario"):
        med_by_label = {f"{m['name']} · {m['scheduled_time']}": m for m in medications}
        label = st.selectbox("Selecciona medicamento", list(med_by_label))
        chosen = med_by_label[label]
        with st.form("edit_medication"):
            c1, c2 = st.columns(2)
            edit_name = c1.text_input("Nombre", value=chosen["name"])
            edit_dose = c2.text_input("Dosis indicada", value=chosen["dose"])
            c3, c4, c5 = st.columns(3)
            edit_time = c3.time_input("Hora (24 h)", value=datetime.strptime(chosen["scheduled_time"], "%H:%M").time(), step=300)
            edit_compartment = c4.text_input("Compartimento", value=chosen["compartment"])
            edit_stock = c5.number_input("Stock", min_value=0, value=int(chosen["stock"] or 0), step=1)
            c6, c7 = st.columns(2)
            edit_min = c6.number_input("Stock mínimo", min_value=0, value=int(chosen["min_stock"] or 0), step=1)
            edit_price = c7.number_input("Precio unitario demo", min_value=0.0, value=float(chosen["unit_price"] or 0), step=500.0)
            if st.form_submit_button("Guardar cambios"):
                try:
                    db.save_medication(patient["id"], edit_name, edit_dose, edit_time.strftime("%H:%M"), edit_compartment, int(edit_stock), int(edit_min), float(edit_price), chosen["id"])
                    st.success("Cambios guardados.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        if st.button("Desactivar medicamento", key="deactivate_med"):
            db.deactivate_medication(patient["id"], chosen["id"])
            st.success("Medicamento desactivado; se conserva el historial.")
            st.rerun()

st.markdown("---")
st.subheader("Registro de dosis de hoy")
logs = db.get_medication_logs(patient["id"])
log_by_id = {m["id"]: m for m in medications}
if medications:
    with st.form("record_dose"):
        selection = st.selectbox("Medicamento", list(log_by_id), format_func=lambda med_id: f"{log_by_id[med_id]['name']} · {log_by_id[med_id]['scheduled_time']}")
        current = next((log["status"] for log in logs if log["medication_id"] == selection), "Pendiente")
        status = st.selectbox("Estado de la dosis", ["Tomado", "Pendiente", "Olvidado"], index=["Tomado", "Pendiente", "Olvidado"].index(current))
        if st.form_submit_button("Guardar estado de dosis"):
            db.record_medication_status(selection, status)
            st.success("Estado de dosis registrado.")
            st.rerun()
    if logs:
        st.dataframe(pd.DataFrame([{"Medicamento": x["name"], "Hora (24 h)": x["scheduled_time"], "Estado": x["status"], "Fecha": x["scheduled_date"]} for x in logs]), use_container_width=True, hide_index=True)
else:
    st.info("Configura un medicamento para comenzar.")
