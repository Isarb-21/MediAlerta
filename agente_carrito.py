"""LangGraph agent for user-directed shopping/replenishment lists.

It compares quantities the caregiver enters with their chosen minimum. It does
not prescribe, choose substitutes, place orders, or handle payment.
"""

from typing import Any, TypedDict
from urllib.parse import quote_plus

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph


SHOPPERS = {
    "Mercado Libre Colombia": "mercadolibre.com.co",
    "Farmatodo": "farmatodo.com.co",
    "Cruz Verde": "cruzverde.com.co",
}


class CartState(TypedDict):
    inventory: list[dict[str, Any]]
    api_key: str
    store: str
    items: list[dict[str, Any]]
    summary: str


def _compare_inventory(state: CartState) -> dict[str, Any]:
    suggestions = []
    for entry in state["inventory"]:
        product = str(entry.get("producto", "")).strip()
        try:
            stock = int(entry.get("stock", 0))
            minimum = int(entry.get("minimo", 0))
            quantity = int(entry.get("reponer", 1))
        except (TypeError, ValueError):
            continue
        if product and stock <= minimum:
            domain = SHOPPERS.get(state["store"], SHOPPERS["Mercado Libre Colombia"])
            search_url = f"https://www.google.com/search?q={quote_plus(f'site:{domain} {product}') }"
            suggestions.append({
                "producto": product,
                "stock_actual": stock,
                "minimo_configurado": minimum,
                "cantidad_sugerida": max(quantity, 1),
                "tienda": state["store"],
                "buscar_en_tienda": search_url,
            })
    return {"items": suggestions}


def _summarize_list(state: CartState) -> dict[str, str]:
    items = state["items"]
    if not items:
        return {"summary": "Ningún producto está en o por debajo del mínimo configurado. No se añadió nada al carrito."}

    local_summary = (
        "Según los mínimos y cantidades que configuraste, revisa: "
        + ", ".join(f"{item['producto']} (cantidad {item['cantidad_sugerida']})" for item in items)
        + ". Confirma presentación, indicación profesional y cantidad en la tienda antes de comprar."
    )
    if not state["api_key"]:
        return {"summary": local_summary}

    model = ChatAnthropic(model="claude-haiku-4-5-20251001", api_key=state["api_key"], max_tokens=260, temperature=0)
    response = model.invoke([
        SystemMessage(content=(
            "Organizas una lista de compras a partir de datos introducidos por el usuario. "
            "No recomiendes medicamentos, dosis, marcas ni sustitutos. No efectúes compras ni pagos. "
            "Resume solo los artículos y cantidades proporcionados y recuerda que el usuario debe revisar y confirmar."
        )),
        HumanMessage(content=f"Artículos ya seleccionados por reglas deterministas: {items}"),
    ])
    return {"summary": str(response.content)}


def build_cart_agent():
    graph = StateGraph(CartState)
    graph.add_node("comparar_stock", _compare_inventory)
    graph.add_node("resumir_reposicion", _summarize_list)
    graph.set_entry_point("comparar_stock")
    graph.add_edge("comparar_stock", "resumir_reposicion")
    graph.add_edge("resumir_reposicion", END)
    return graph.compile()


def analizar_reposicion(inventory: list[dict[str, Any]], store: str, api_key: str = "") -> dict[str, Any]:
    result = build_cart_agent().invoke({
        "inventory": inventory,
        "api_key": api_key,
        "store": store,
        "items": [],
        "summary": "",
    })
    return {"items": result["items"], "resumen": result["summary"]}
