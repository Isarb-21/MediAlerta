import json
import os
from typing import Any, TypedDict

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph


load_dotenv()


# =========================================================
# ESTADO DEL AGENTE
# =========================================================

class EstadoMediAlerta(TypedDict):
    pregunta: str
    datos_paciente: dict[str, Any]
    api_key: str

    errores_validacion: list[str]
    alertas: list[dict[str, Any]]
    contexto: str
    respuesta_preliminar: str
    respuesta_final: str


# =========================================================
# CONFIGURACIÓN DETERMINISTA DE LA DEMOSTRACIÓN
# =========================================================

LIMITES_DEMO = {
    "bpm_minimo": 50,
    "bpm_maximo": 100,
    "spo2_minimo": 94,
    "temperatura_maxima": 38.0,
    "inventario_bajo": 2,
}


PALABRAS_EMERGENCIA = [
    "no puede respirar",
    "dificultad para respirar",
    "perdió el conocimiento",
    "perdio el conocimiento",
    "está inconsciente",
    "esta inconsciente",
    "dolor fuerte en el pecho",
    "dolor intenso en el pecho",
    "convulsión",
    "convulsion",
    "convulsiones",
    "sangrado abundante",
    "empeoramiento repentino",
]


PROMPT_SISTEMA = """
Eres MediAlerta, un agente inteligente de apoyo informativo para cuidadores.

Tu función es ayudar al cuidador a entender los datos registrados y
decidir qué información debe revisar.

Todos los datos pertenecen a una demostración y son simulados.

REGLAS OBLIGATORIAS:

1. No diagnostiques enfermedades.
2. No afirmes que una lectura aislada confirma una enfermedad.
3. No recomiendes iniciar, suspender, repetir o cambiar medicamentos.
4. No recomiendes modificar una dosis.
5. No inventes información que no aparezca en el contexto.
6. Si no hay información suficiente, indícalo claramente.
7. Explica las alertas generadas por las reglas deterministas.
8. Puedes proponer acciones seguras como:
   - verificar que una medición se tomó correctamente;
   - revisar si una dosis quedó registrada;
   - revisar físicamente el inventario;
   - registrar observaciones;
   - contactar al profesional responsable.
9. Ante síntomas graves o empeoramiento repentino, indica que se debe
   contactar inmediatamente a los servicios de emergencia locales.
10. La conversación con el agente no debe retrasar la atención de emergencia.
11. No reemplazas al médico, al farmacéutico ni al personal de salud.
12. Responde en español y utiliza lenguaje sencillo.
13. Diferencia claramente entre:
   - datos registrados;
   - alertas generadas por reglas;
   - acciones seguras sugeridas.

La respuesta debe ser breve, organizada y comprensible para un cuidador.
"""


# =========================================================
# DATOS SIMULADOS INDEPENDIENTES
# =========================================================

def obtener_datos_simulados() -> dict[str, Any]:
    """
    Devuelve datos independientes de demostración.

    No consulta ESP32, Firebase, Adafruit IO ni servicios de emergencia.
    """

    return {
        "modo_demo": True,
        "fuente": "Datos simulados locales",
        "paciente": {
            "nombre": "Paciente de demostración",
            "edad": 72,
        },
        "signos_vitales": {
            "bpm": 76,
            "spo2": 98,
            "temperatura": 36.7,
            "fecha_registro": "2026-11-08 08:45",
        },
        "medicamentos": [
            {
                "medicamento": "Losartán",
                "hora": "08:00",
                "dosis": "50 mg",
                "estado": "Tomado",
            },
            {
                "medicamento": "Metformina",
                "hora": "08:30",
                "dosis": "500 mg",
                "estado": "Tomado",
            },
            {
                "medicamento": "Atorvastatina",
                "hora": "20:00",
                "dosis": "20 mg",
                "estado": "Pendiente",
            },
            {
                "medicamento": "Vitamina D",
                "hora": "21:00",
                "dosis": "1 cápsula",
                "estado": "Olvidado",
            },
        ],
        "adherencia": {
            "periodo": "Semana actual",
            "porcentaje": 90,
            "dosis_tomadas": 18,
            "dosis_faltantes": 2,
        },
        "inventario": [
            {
                "compartimento": "A1",
                "medicamento": "Losartán",
                "stock": 12,
                "capacidad": 14,
            },
            {
                "compartimento": "B2",
                "medicamento": "Metformina",
                "stock": 9,
                "capacidad": 10,
            },
            {
                "compartimento": "C1",
                "medicamento": "Atorvastatina",
                "stock": 2,
                "capacidad": 7,
            },
            {
                "compartimento": "D3",
                "medicamento": "Vitamina D",
                "stock": 0,
                "capacidad": 5,
            },
        ],
    }


# =========================================================
# PASO 1: DETECCIÓN DE EMERGENCIA
# =========================================================

def contiene_situacion_de_emergencia(pregunta: str) -> bool:
    texto = pregunta.lower().strip()

    return any(
        palabra in texto
        for palabra in PALABRAS_EMERGENCIA
    )


def respuesta_de_emergencia() -> str:
    return (
        "⚠️ La situación descrita puede requerir atención inmediata.\n\n"
        "Contacta ahora mismo a los servicios de emergencia locales y "
        "al profesional responsable. No esperes una respuesta adicional "
        "del agente y no permitas que esta conversación retrase la atención.\n\n"
        "En Colombia puedes comunicarte con la línea nacional de "
        "emergencias 123.\n\n"
        "MediAlerta no diagnostica y no reemplaza al personal de salud."
    )


# =========================================================
# PASO 2: VALIDACIÓN DE DATOS
# =========================================================

def validar_datos(estado: EstadoMediAlerta) -> dict[str, Any]:
    datos = estado["datos_paciente"]
    errores = []

    secciones_requeridas = [
        "paciente",
        "signos_vitales",
        "medicamentos",
        "adherencia",
        "inventario",
    ]

    for seccion in secciones_requeridas:
        if seccion not in datos:
            errores.append(
                f"No está disponible la sección: {seccion}."
            )

    signos = datos.get("signos_vitales", {})

    for nombre in ["bpm", "spo2", "temperatura"]:
        valor = signos.get(nombre)

        if valor is not None and not isinstance(valor, (int, float)):
            errores.append(
                f"El valor de {nombre} no tiene un formato numérico válido."
            )

    medicamentos = datos.get("medicamentos")

    if medicamentos is not None and not isinstance(medicamentos, list):
        errores.append(
            "La información de medicamentos debe ser una lista."
        )

    inventario = datos.get("inventario")

    if inventario is not None and not isinstance(inventario, list):
        errores.append(
            "La información del inventario debe ser una lista."
        )

    return {
        "errores_validacion": errores,
    }


# =========================================================
# PASO 3: REGLAS DETERMINISTAS DE ALERTA
# =========================================================

def evaluar_reglas(estado: EstadoMediAlerta) -> dict[str, Any]:
    datos = estado["datos_paciente"]
    alertas = []

    signos = datos.get("signos_vitales", {})

    bpm = signos.get("bpm")
    spo2 = signos.get("spo2")
    temperatura = signos.get("temperatura")

    if isinstance(bpm, (int, float)):
        if bpm < LIMITES_DEMO["bpm_minimo"]:
            alertas.append({
                "codigo": "BPM_BAJO",
                "prioridad": "Alta",
                "origen": "Regla determinista",
                "motivo": (
                    f"El BPM registrado es {bpm} y está por debajo del "
                    f"límite configurado de "
                    f"{LIMITES_DEMO['bpm_minimo']}."
                ),
                "dato_a_verificar": (
                    "Verificar que la medición se haya tomado correctamente."
                ),
            })

        elif bpm > LIMITES_DEMO["bpm_maximo"]:
            alertas.append({
                "codigo": "BPM_ALTO",
                "prioridad": "Alta",
                "origen": "Regla determinista",
                "motivo": (
                    f"El BPM registrado es {bpm} y supera el límite "
                    f"configurado de {LIMITES_DEMO['bpm_maximo']}."
                ),
                "dato_a_verificar": (
                    "Verificar que la medición se haya tomado correctamente."
                ),
            })

    if (
        isinstance(spo2, (int, float))
        and spo2 < LIMITES_DEMO["spo2_minimo"]
    ):
        alertas.append({
            "codigo": "SPO2_BAJA",
            "prioridad": "Alta",
            "origen": "Regla determinista",
            "motivo": (
                f"La SpO2 registrada es {spo2}% y está por debajo del "
                f"límite configurado de "
                f"{LIMITES_DEMO['spo2_minimo']}%."
            ),
            "dato_a_verificar": (
                "Revisar el sensor y verificar nuevamente la medición."
            ),
        })

    if (
        isinstance(temperatura, (int, float))
        and temperatura >= LIMITES_DEMO["temperatura_maxima"]
    ):
        alertas.append({
            "codigo": "TEMPERATURA_ALTA",
            "prioridad": "Alta",
            "origen": "Regla determinista",
            "motivo": (
                f"La temperatura registrada es {temperatura} °C y alcanzó "
                f"el límite configurado de "
                f"{LIMITES_DEMO['temperatura_maxima']} °C."
            ),
            "dato_a_verificar": (
                "Verificar el dispositivo y repetir correctamente la medición."
            ),
        })

    for medicamento in datos.get("medicamentos", []):
        nombre = medicamento.get(
            "medicamento",
            "Medicamento sin identificar",
        )

        estado_medicamento = str(
            medicamento.get("estado", "")
        ).lower()

        if estado_medicamento == "olvidado":
            alertas.append({
                "codigo": "DOSIS_OLVIDADA",
                "prioridad": "Media",
                "origen": "Regla determinista",
                "motivo": (
                    f"{nombre} aparece registrado con estado Olvidado."
                ),
                "dato_a_verificar": (
                    "Revisar si el registro de la dosis es correcto. "
                    "No administrar ni repetir una dosis fuera del horario "
                    "sin consultar al profesional responsable."
                ),
            })

        elif estado_medicamento == "pendiente":
            alertas.append({
                "codigo": "DOSIS_PENDIENTE",
                "prioridad": "Informativa",
                "origen": "Regla determinista",
                "motivo": (
                    f"{nombre} aparece registrado con estado Pendiente."
                ),
                "dato_a_verificar": (
                    "Revisar la hora programada y el registro disponible."
                ),
            })

    for elemento in datos.get("inventario", []):
        stock = elemento.get("stock")
        medicamento = elemento.get(
            "medicamento",
            "Medicamento sin identificar",
        )
        compartimento = elemento.get(
            "compartimento",
            "Sin identificar",
        )

        if not isinstance(stock, (int, float)):
            continue

        if stock == 0:
            alertas.append({
                "codigo": "INVENTARIO_VACIO",
                "prioridad": "Media",
                "origen": "Regla determinista",
                "motivo": (
                    f"El compartimento {compartimento} de {medicamento} "
                    "registra 0 unidades."
                ),
                "dato_a_verificar": (
                    "Revisar físicamente el compartimento y confirmar "
                    "el inventario registrado."
                ),
            })

        elif stock <= LIMITES_DEMO["inventario_bajo"]:
            alertas.append({
                "codigo": "INVENTARIO_BAJO",
                "prioridad": "Baja",
                "origen": "Regla determinista",
                "motivo": (
                    f"El compartimento {compartimento} de {medicamento} "
                    f"registra {stock} unidades."
                ),
                "dato_a_verificar": (
                    "Revisar físicamente la cantidad disponible."
                ),
            })

    return {
        "alertas": alertas,
    }


# =========================================================
# PASO 4: CONSTRUCCIÓN DEL CONTEXTO
# =========================================================

def construir_contexto(
    estado: EstadoMediAlerta,
) -> dict[str, Any]:

    contexto_estructurado = {
        "advertencia": (
            "Todos los datos son simulados y pertenecen a una demostración."
        ),
        "datos_paciente": estado["datos_paciente"],
        "alertas_generadas_por_reglas": estado["alertas"],
        "errores_de_validacion": estado["errores_validacion"],
        "limitacion": (
            "El sistema no está conectado al ESP32, Firebase, "
            "Adafruit IO ni a servicios de emergencia."
        ),
    }

    contexto_texto = json.dumps(
        contexto_estructurado,
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    return {
        "contexto": contexto_texto,
    }


# =========================================================
# RESPUESTAS LOCALES SIN CLAUDE
# =========================================================

def obtener_medicamentos_pendientes(
    datos: dict[str, Any],
) -> list[dict[str, Any]]:

    estados_revision = {
        "pendiente",
        "olvidado",
        "retraso",
    }

    return [
        medicamento
        for medicamento in datos.get("medicamentos", [])
        if str(medicamento.get("estado", "")).lower()
        in estados_revision
    ]


def respuesta_local(
    pregunta: str,
    datos: dict[str, Any],
    alertas: list[dict[str, Any]],
) -> str:

    texto = pregunta.lower()

    if contiene_situacion_de_emergencia(pregunta):
        return respuesta_de_emergencia()

    if "resumen" in texto or "estado del paciente" in texto:
        signos = datos.get("signos_vitales", {})
        adherencia = datos.get("adherencia", {})
        pendientes = obtener_medicamentos_pendientes(datos)

        return (
            "Estos son datos simulados de demostración.\n\n"
            f"• BPM registrado: {signos.get('bpm', 'sin información')}.\n"
            f"• SpO2 registrada: "
            f"{signos.get('spo2', 'sin información')}%.\n"
            f"• Temperatura registrada: "
            f"{signos.get('temperatura', 'sin información')} °C.\n"
            f"• Adherencia semanal: "
            f"{adherencia.get('porcentaje', 'sin información')}%.\n"
            f"• Registros de medicamentos que requieren revisión: "
            f"{len(pendientes)}.\n"
            f"• Alertas generadas por reglas: {len(alertas)}.\n\n"
            "Esta información no constituye un diagnóstico."
        )

    if (
        "medicamento" in texto
        or "medicamentos" in texto
        or "dosis" in texto
        or "pendiente" in texto
    ):
        pendientes = obtener_medicamentos_pendientes(datos)

        if not pendientes:
            return (
                "No aparecen medicamentos pendientes en los datos simulados."
            )

        lineas = []

        for medicamento in pendientes:
            lineas.append(
                f"• {medicamento.get('medicamento')}: "
                f"{medicamento.get('estado')}, "
                f"hora registrada {medicamento.get('hora')}."
            )

        return (
            "Datos simulados. Los siguientes registros requieren revisión:\n\n"
            + "\n".join(lineas)
            + "\n\nVerifica los registros disponibles. No repitas ni "
              "modifiques una dosis sin consultar al profesional responsable."
        )

    if "adherencia" in texto:
        adherencia = datos.get("adherencia", {})

        if not adherencia:
            return (
                "No hay información suficiente sobre la adherencia."
            )

        return (
            "Datos simulados de demostración.\n\n"
            f"• Periodo: {adherencia.get('periodo', 'sin información')}.\n"
            f"• Adherencia registrada: "
            f"{adherencia.get('porcentaje', 'sin información')}%.\n"
            f"• Dosis tomadas: "
            f"{adherencia.get('dosis_tomadas', 'sin información')}.\n"
            f"• Dosis faltantes: "
            f"{adherencia.get('dosis_faltantes', 'sin información')}.\n\n"
            "Estos datos describen registros de la demostración y no "
            "constituyen una evaluación clínica."
        )

    if (
        "inventario" in texto
        or "compartimento" in texto
        or "stock" in texto
        or "vacío" in texto
        or "vacio" in texto
    ):
        inventario_revision = [
            elemento
            for elemento in datos.get("inventario", [])
            if isinstance(elemento.get("stock"), (int, float))
            and elemento["stock"] <= LIMITES_DEMO["inventario_bajo"]
        ]

        if not inventario_revision:
            return (
                "No aparecen inventarios bajos en los datos simulados."
            )

        lineas = []

        for elemento in inventario_revision:
            lineas.append(
                f"• {elemento.get('medicamento')}: "
                f"{elemento.get('stock')} unidades en el compartimento "
                f"{elemento.get('compartimento')}."
            )

        return (
            "Datos simulados. Conviene revisar estos compartimentos:\n\n"
            + "\n".join(lineas)
            + "\n\nVerifica físicamente el contenido antes de actualizar "
              "el registro."
        )

    if "alerta" in texto or "alertas" in texto:
        if not alertas:
            return (
                "No se generaron alertas con las reglas configuradas "
                "para la demostración."
            )

        lineas = []

        for alerta in alertas:
            lineas.append(
                f"• {alerta['codigo']} | "
                f"Prioridad: {alerta['prioridad']}\n"
                f"  Motivo: {alerta['motivo']}\n"
                f"  Verificar: {alerta['dato_a_verificar']}"
            )

        return (
            "Datos simulados. Alertas generadas por reglas deterministas:\n\n"
            + "\n\n".join(lineas)
            + "\n\nLas alertas no representan un diagnóstico."
        )

    if (
        "presión" in texto
        or "presion" in texto
        or "glucosa" in texto
        or "peso" in texto
    ):
        return (
            "No hay información suficiente para responder esa pregunta. "
            "Los datos simulados disponibles no contienen ese registro."
        )

    return (
        "No tengo información suficiente para responder con los datos "
        "disponibles. Puedes preguntar por el resumen del paciente, "
        "medicamentos pendientes, adherencia, inventario o alertas. "
        "Todos los datos son simulados."
    )


# =========================================================
# PASO 5: AGENTE IA CON CLAUDE
# =========================================================

def generar_respuesta_ia(
    estado: EstadoMediAlerta,
) -> dict[str, Any]:

    pregunta = estado["pregunta"]

    if contiene_situacion_de_emergencia(pregunta):
        return {
            "respuesta_preliminar": respuesta_de_emergencia(),
        }

    if estado["errores_validacion"]:
        return {
            "respuesta_preliminar": (
                "No puedo analizar completamente la información porque "
                "se encontraron estos problemas:\n\n• "
                + "\n• ".join(estado["errores_validacion"])
            ),
        }

    if not estado["api_key"]:
        respuesta = respuesta_local(
            pregunta=pregunta,
            datos=estado["datos_paciente"],
            alertas=estado["alertas"],
        )

        return {
            "respuesta_preliminar": respuesta,
        }

    try:
        modelo = ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            api_key=estado["api_key"],
            max_tokens=700,
            temperature=0,
        )

        mensajes = [
            SystemMessage(content=PROMPT_SISTEMA),
            HumanMessage(
                content=(
                    "Contexto disponible para responder:\n\n"
                    f"{estado['contexto']}\n\n"
                    "Pregunta realizada por el cuidador:\n"
                    f"{pregunta}"
                )
            ),
        ]

        respuesta = modelo.invoke(mensajes)

        contenido = respuesta.content

        if isinstance(contenido, list):
            contenido = " ".join(
                str(elemento)
                for elemento in contenido
            )

        return {
            "respuesta_preliminar": str(contenido),
        }

    except Exception:
        respuesta = respuesta_local(
            pregunta=pregunta,
            datos=estado["datos_paciente"],
            alertas=estado["alertas"],
        )

        return {
            "respuesta_preliminar": respuesta,
        }


# =========================================================
# PASO 6: REVISIÓN DE SEGURIDAD
# =========================================================

def revisar_seguridad(
    estado: EstadoMediAlerta,
) -> dict[str, Any]:

    pregunta = estado["pregunta"]
    respuesta = estado["respuesta_preliminar"].strip()

    if contiene_situacion_de_emergencia(pregunta):
        return {
            "respuesta_final": respuesta_de_emergencia(),
        }

    if not respuesta:
        respuesta = (
            "No hay información suficiente para responder con los "
            "datos disponibles."
        )

    expresiones_prohibidas = [
        "debe tomar otra dosis",
        "debe repetir la dosis",
        "repita la dosis",
        "suspenda el medicamento",
        "deje de tomar",
        "aumente la dosis",
        "reduzca la dosis",
        "cambie la dosis",
        "tiene hipertensión",
        "tiene diabetes",
        "está diagnosticado",
        "esta diagnosticado",
        "confirmamos que tiene",
    ]

    respuesta_minuscula = respuesta.lower()

    contiene_recomendacion_insegura = any(
        expresion in respuesta_minuscula
        for expresion in expresiones_prohibidas
    )

    if contiene_recomendacion_insegura:
        respuesta = (
            "No puedo recomendar iniciar, suspender, repetir o cambiar "
            "medicamentos o dosis.\n\n"
            "Puedes verificar el registro disponible y contactar al médico "
            "o farmacéutico responsable si existen dudas.\n\n"
            "Todos los datos pertenecen a una demostración."
        )

    if "simulad" not in respuesta.lower():
        respuesta += (
            "\n\n⚠️ Los datos pertenecen a una demostración y son "
            "simulados."
        )

    if (
        "diagnóstico" not in respuesta.lower()
        and "diagnostico" not in respuesta.lower()
    ):
        respuesta += (
            " Esta respuesta no constituye un diagnóstico ni reemplaza "
            "la evaluación de un profesional de salud."
        )

    return {
        "respuesta_final": respuesta,
    }


# =========================================================
# CONSTRUCCIÓN DEL FLUJO LANGGRAPH
# =========================================================

def construir_agente():
    grafo = StateGraph(EstadoMediAlerta)

    grafo.add_node("validar_datos", validar_datos)
    grafo.add_node("evaluar_reglas", evaluar_reglas)
    grafo.add_node("construir_contexto", construir_contexto)
    grafo.add_node("generar_respuesta", generar_respuesta_ia)
    grafo.add_node("revisar_seguridad", revisar_seguridad)

    grafo.set_entry_point("validar_datos")

    grafo.add_edge("validar_datos", "evaluar_reglas")
    grafo.add_edge("evaluar_reglas", "construir_contexto")
    grafo.add_edge("construir_contexto", "generar_respuesta")
    grafo.add_edge("generar_respuesta", "revisar_seguridad")
    grafo.add_edge("revisar_seguridad", END)

    return grafo.compile()


# =========================================================
# FUNCIÓN PRINCIPAL PARA CONSULTAR EL AGENTE
# =========================================================

def preguntar_agente(
    pregunta: str,
    datos_paciente: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> str:

    if not pregunta or not pregunta.strip():
        return (
            "Escribe una pregunta sobre los datos simulados del paciente."
        )

    if datos_paciente is None:
        datos_paciente = obtener_datos_simulados()

    if api_key is None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if contiene_situacion_de_emergencia(pregunta):
        return respuesta_de_emergencia()

    agente = construir_agente()

    resultado = agente.invoke({
        "pregunta": pregunta.strip(),
        "datos_paciente": datos_paciente,
        "api_key": api_key,
        "errores_validacion": [],
        "alertas": [],
        "contexto": "",
        "respuesta_preliminar": "",
        "respuesta_final": "",
    })

    return resultado["respuesta_final"]


# =========================================================
# PRUEBA DEL ARCHIVO DESDE LA TERMINAL
# =========================================================

def iniciar_chat_terminal():
    print("=" * 60)
    print("MEDIALERTA")
    print("Agente de apoyo para cuidadores")
    print("=" * 60)
    print("Todos los datos son simulados.")
    print("Escribe 'salir' para finalizar.\n")

    datos = obtener_datos_simulados()

    while True:
        pregunta = input("Cuidador: ").strip()

        if pregunta.lower() in {"salir", "cerrar", "terminar"}:
            print("\nMediAlerta: Conversación finalizada.")
            break

        respuesta = preguntar_agente(
            pregunta=pregunta,
            datos_paciente=datos,
        )

        print(f"\nMediAlerta:\n{respuesta}\n")


if __name__ == "__main__":
    iniciar_chat_terminal()