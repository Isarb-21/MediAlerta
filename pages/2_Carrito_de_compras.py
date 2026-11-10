"""Inventario-aware shopping assistant and persisted demo checkout."""

from datetime import datetime

import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="MediAlerta | Carrito", page_icon="🛒", layout="wide")
db.init_db()
if not st.session_state.get("logged_in"):
    st.warning("Inicia sesión desde MediAlerta para continuar.")
    st.stop()

username = st.session_state.get("user", "cuidador")
patient = db.get_patient()
cart_id = db.get_active_cart(username)
st.markdown('<p class="eyebrow">REABASTECIMIENTO</p>', unsafe_allow_html=True)
st.title("Carrito de compras 🛒")
st.caption("El asistente solo sugiere reponer productos ya configurados en el inventario. Revisa y confirma el pedido.")
st.info("Demo educativa: catálogo y precios de ejemplo. No es una farmacia ni procesa pagos reales. Nunca ingreses datos de tarjeta o CVV.")

inventory = db.get_inventory(patient["id"])
request = st.text_input("¿Qué necesitas?", placeholder="Ej.: revisar lo que está bajo, reponer Losartán")
if st.button("🤖 Analizar inventario y preparar sugerencia", type="primary"):
    text = request.casefold()
    requested = [item for item in inventory if item["name"].casefold() in text]
    if any(word in text for word in ("todo", "bajo", "reponer", "faltante", "inventario", "stock")) or not text.strip():
        suggestions = [item for item in inventory if item["stock"] <= item["min_stock"]]
        if requested:
            suggestions = list({item["medication_id"]: item for item in suggestions + requested}.values())
    elif requested:
        suggestions = requested
    else:
        suggestions = []
    st.session_state["shopping_suggestions"] = suggestions
    st.session_state["shopping_agent_note"] = (
        "Encontré productos configurados que alcanzaron el stock mínimo. Las cantidades sugeridas solo buscan llevar el inventario al nivel mínimo configurado."
        if suggestions else "No encontré ese producto entre los medicamentos configurados. Agrega o configura productos en la sección Medicamentos; el asistente no recomienda tratamientos nuevos."
    )

if st.session_state.get("shopping_agent_note"):
    st.info(st.session_state["shopping_agent_note"])
for item in st.session_state.get("shopping_suggestions", []):
    target = max(1, int(item["min_stock"] + 2 - item["stock"]))
    col1, col2, col3 = st.columns([3, 2, 2])
    col1.write(f"**{item['name']}** · Compartimento {item['compartment']} · Stock actual: {item['stock']}")
    col2.write(f"Cantidad sugerida: {target} · ${item['unit_price']:,.0f} c/u")
    if col3.button("Agregar sugerencia", key=f"add_{item['medication_id']}"):
        db.add_cart_item(cart_id, item["medication_id"], target)
        st.success(f"{item['name']} agregado al carrito.")

st.markdown("---")
st.subheader("Agregar/ajustar productos del catálogo")
if inventory:
    with st.form("add_cart_item"):
        options = {f"{item['name']} — ${item['unit_price']:,.0f} (stock {item['stock']})": item for item in inventory}
        label = st.selectbox("Producto configurado", list(options))
        quantity = st.number_input("Cantidad", min_value=1, max_value=100, value=1, step=1)
        if st.form_submit_button("Agregar al carrito"):
            db.add_cart_item(cart_id, options[label]["medication_id"], int(quantity))
            st.success("Producto guardado en el carrito.")
            st.rerun()

st.subheader("Tu carrito")
cart = db.get_cart(cart_id)
if not cart:
    st.info("El carrito está vacío. Ejecuta el asistente o agrega un producto del catálogo.")
else:
    frame = pd.DataFrame([{"Producto": x["name"], "Dosis registrada": x["dose"], "Compartimento": x["compartment"], "Cantidad": x["quantity"], "Precio unitario": x["unit_price"], "Subtotal": x["subtotal"]} for x in cart])
    st.dataframe(frame, use_container_width=True, hide_index=True)
    total = sum(float(x["subtotal"]) for x in cart)
    st.markdown(f"### Total demo: **${total:,.0f} COP**")
    with st.expander("Quitar un producto"):
        remove_options = {f"{x['name']} (x{x['quantity']})": x for x in cart}
        selected = st.selectbox("Producto", list(remove_options), key="remove_item")
        if st.button("Quitar del carrito"):
            db.remove_cart_item(remove_options[selected]["id"], cart_id)
            st.rerun()

    st.markdown("---")
    st.subheader("Confirmar pedido")
    with st.form("checkout"):
        c1, c2 = st.columns(2)
        delivery_name = c1.text_input("Nombre de quien recibe", value=patient.get("caregiver_name", ""))
        delivery_phone = c2.text_input("Teléfono de contacto", value=patient.get("phone", ""))
        address = st.text_input("Dirección de entrega", placeholder="Dirección para esta demostración")
        payment = st.radio("Método de pago", ["Efectivo contra entrega", "Tarjeta (simulada)"], horizontal=True)
        if payment == "Tarjeta (simulada)":
            st.warning("Pago ficticio aprobado al confirmar. No solicitamos ni almacenamos número de tarjeta, vencimiento ni CVV. Una integración real debe usar una pasarela de pago certificada.")
        else:
            st.caption("El pago se marca pendiente contra entrega; no se cobra desde la demo.")
        confirmed = st.checkbox("Revisé el pedido y autorizo crear esta orden de demostración.")
        submit = st.form_submit_button("Confirmar pedido", type="primary")
        if submit:
            if not confirmed:
                st.error("Marca la confirmación antes de crear el pedido.")
            else:
                try:
                    order_id = db.create_order(cart_id, username, patient["id"], delivery_name, delivery_phone, address, payment)
                    st.session_state["last_order_id"] = order_id
                    st.success(f"Pedido demo #{order_id} creado a las {datetime.now().strftime('%H:%M')}.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))

if st.session_state.get("last_order_id"):
    st.success(f"Último pedido creado: #{st.session_state['last_order_id']}")

st.markdown("---")
st.subheader("Historial de pedidos")
orders = db.get_orders(username)
if orders:
    for order in orders:
        with st.expander(f"Pedido #{order['id']} · {datetime.fromisoformat(order['created_at']).strftime('%d/%m/%Y %H:%M')} · ${order['total']:,.0f} COP · {order['payment_method']}"):
            st.write(f"Estado: {order['order_status']} · Pago: {order['payment_status']}")
            st.write(f"Entrega: {order['delivery_name']} · {order['delivery_phone']} · {order['delivery_address']}")
            for item in order["items"]:
                st.write(f"{item['medication_name']} × {item['quantity']} — ${item['subtotal']:,.0f}")
else:
    st.caption("Aún no hay pedidos guardados.")
