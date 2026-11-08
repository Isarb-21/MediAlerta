from typing import TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph


class AssistantState(TypedDict):
    question: str
    patient_context: str
    api_key: str
    answer: str


SYSTEM_PROMPT = """Eres MediAlerta, un agente de apoyo informativo para cuidadores. Responde en español, de forma clara y breve, usando únicamente el contexto compartido.

Límites de seguridad:
- No diagnostiques, no prescribas ni recomiendes iniciar, suspender o cambiar dosis de medicamentos.
- No afirmes que una lectura aislada confirma una enfermedad o una emergencia.
- Distingue claramente los datos de demostración de una evaluación clínica.
- Si el usuario describe síntomas graves o empeoramiento repentino, recomienda contactar inmediatamente los servicios de emergencia locales y al profesional de salud; no retrases esa atención por seguir conversando.
- Para dudas sobre tratamiento, indica consultar al médico o farmacéutico responsable.
- Si no hay datos suficientes, dilo y pide información pertinente sin solicitar información personal innecesaria.
- Ofrece acciones seguras para el cuidador: verificar la medición, registrar observaciones y contactar al profesional responsable.
"""


def _answer_with_claude(state: AssistantState) -> dict:
    model = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=state["api_key"],
        max_tokens=700,
    )
    response = model.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "Contexto actual del paciente (datos de demo):\n"
                    f"{state['patient_context']}\n\n"
                    f"Pregunta del cuidador: {state['question']}"
                )
            ),
        ]
    )
    return {"answer": response.content}


def build_assistant_graph():
    """Construye un flujo LangGraph de respuesta con límites de seguridad clínica."""
    graph = StateGraph(AssistantState)
    graph.add_node("assistant", _answer_with_claude)
    graph.set_entry_point("assistant")
    graph.add_edge("assistant", END)
    return graph.compile()


def ask_assistant(question: str, patient_context: str, api_key: str) -> str:
    """Invoca el agente MediAlerta. La app debe proveer un fallback sin conexión."""
    result = build_assistant_graph().invoke(
        {
            "question": question.strip(),
            "patient_context": patient_context,
            "api_key": api_key,
            "answer": "",
        }
    )
    return result["answer"]
