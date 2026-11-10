import os

import streamlit as st
from dotenv import load_dotenv

from agente_carrito import SHOPPERS, analizar_reposicion

st.markdown('<p class="eyebrow">REPOSICIÓN BAJO TU CONTROL</p>', unsafe_allow_html=True)
st.title("Carrito de compras 🛒")
st.caption("El agente organiza una lista con base en el producto, stock y mínimo que tú registres.")
st.warning("No prescribe, no sustituye medicamentos, no realiza pedidos ni pagos. Los enlaces abren búsquedas en la tienda para que tú verifiques y confirmes cada compra.")

if not st.session_state.get("logged_in"):
    st.warning("Inicia sesión desde MediAlerta para usar el carrito.")
    st.stop()

if "cart_inventory" not in st.session_state:
    st.session_state["cart_inventory"] = []
if "shopping_cart" not in st.session_state:
    st.session_state["shopping_cart"] = []

with st.expander("Añadir producto", expanded=not st.session_state["cart_inventory"]):
    with st.form("add_product", clear_on_submit=True):
        product = st.text_input("Nombre exacto del producto indicado por ti", placeholder="Ej.: producto o insumo")
        store = st.selectbox("Tienda para buscar", list(SHOPPERS))
        col1, col2, col3 = st.columns(3)
        stock = col1.number_input("Cantidad actual", min_value=0, step=1, value=0)
        minimum = col2.number_input("Mínimo que defines", min_value=0, step=1, value=2)
        quantity = col3.number_input("Cantidad que quieres reponer", min_value=1, step=1, value=1)
        if st.form_submit_button("Guardar producto", use_container_width=True):
            if not product.strip():
                st.error("Escribe el nombre del producto.")
            else:
                st.session_state["cart_inventory"].append({
                    "producto": product.strip(),
                    "stock": int(stock),
                    "minimo": int(minimum),
                    "reponer": int(quantity),
                    "tienda": store,
                })
                st.success("Producto guardado.")
                st.rerun()

inventory = st.session_state["cart_inventory"]
if inventory:
    st.markdown("### Productos registrados")
    st.dataframe(inventory, use_container_width=True, hide_index=True)
    chosen_store = st.selectbox("Tienda para esta lista", list(SHOPPERS), key="cart_store")
    if st.button("🤖 Analizar stock y preparar carrito", type="primary", use_container_width=True):
        with st.spinner("El agente compara stock con tus mínimos..."):
            try:
                result = analizar_reposicion(
                    inventory,
                    store=chosen_store,
                    api_key=os.getenv("ANTHROPIC_API_KEY", ""),
                )
                st.session_state["cart_analysis"] = result
                st.session_state["cart_store_result"] = chosen_store
            except Exception as error:
                st.error(f"No se pudo completar el análisis ({type(error).__name__}).")

    result = st.session_state.get("cart_analysis")
    if result:
        st.markdown("### Resultado del agente")
        st.info(result["resumen"])
        suggestions = result["items"]
        if suggestions:
            st.markdown("### Artículos para revisar")
            st.dataframe(
                [{key: value for key, value in item.items() if key != "buscar_en_tienda"} for item in suggestions],
                use_container_width=True,
                hide_index=True,
            )
            if st.button("Añadir artículos a mi carrito", use_container_width=True):
                cart = st.session_state["shopping_cart"]
                for item in suggestions:
                    existing = next((entry for entry in cart if entry["producto"].casefold() == item["producto"].casefold()), None)
                    if existing:
                        existing["cantidad"] = item["cantidad_sugerida"]
                        existing["tienda"] = item["tienda"]
                        existing["buscar_en_tienda"] = item["buscar_en_tienda"]
                    else:
                        cart.append({
                            "producto": item["producto"],
                            "cantidad": item["cantidad_sugerida"],
                            "tienda": item["tienda"],
                            "buscar_en_tienda": item["buscar_en_tienda"],
                        })
                st.session_state["shopping_cart"] = cart
                st.success("Lista preparada. Verifica los productos en la tienda antes de comprar.")
                st.rerun()
        else:
            st.success("No hay productos por debajo de los mínimos que configuraste.")

st.markdown("---")
st.markdown("### Mi carrito")
cart = st.session_state["shopping_cart"]
if not cart:
    st.caption("Aún no tienes artículos en el carrito.")
else:
    for index, item in enumerate(cart):
        col_product, col_link, col_remove = st.columns([3, 2, 1])
        col_product.markdown(f"**{item['producto']}** · Cantidad {item['cantidad']}")
        col_link.link_button("Buscar en tienda", item["buscar_en_tienda"], use_container_width=True)
        if col_remove.button("Quitar", key=f"remove_{index}"):
            cart.pop(index)
            st.session_state["shopping_cart"] = cart
            st.rerun()
    st.caption("Los enlaces son búsquedas; no agregan productos al carrito de la tienda ni efectúan pagos.")
    if st.button("Vaciar mi carrito"):
        st.session_state["shopping_cart"] = []
        st.session_state.pop("cart_analysis", None)
        st.rerun()
