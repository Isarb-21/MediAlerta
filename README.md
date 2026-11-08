# MediAlerta — demo MVP

Prototipo web para la sustentación de MediAlerta, implementado con Python y Streamlit. Incluye inicio de sesión de demostración, dashboard de signos vitales, medicamentos, historial, alertas, inventario del pastillero y perfil del paciente.

> **Importante:** esta versión usa datos de ejemplo locales. No está conectada a un dispositivo ESP32, Adafruit IO, Firebase, autenticación real ni notificaciones push. La información y las recomendaciones son demostrativas; no se deben usar para decisiones médicas reales.

## Requisitos

- Python 3.10 o superior
- pip

## Instalación y ejecución

Desde la carpeta `MediAlerta`:

```bash
python -m venv .venv
```

Activa el entorno virtual:

- Windows PowerShell: `.venv\\Scripts\\Activate.ps1`
- macOS/Linux: `source .venv/bin/activate`

Instala las dependencias e inicia Streamlit:

```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

Si el comando `streamlit` no aparece en tu terminal, usa `python -m streamlit` (especialmente en Windows con Python instalado sin PATH global). Abre en el navegador la dirección que indique Streamlit (normalmente `http://localhost:8501`). En el inicio de sesión de demo, ingresa cualquier usuario y contraseña no vacíos.

## Uso opcional de Claude

La recomendación de cuidado usa reglas locales si no configuras una clave de Anthropic. Para probar generación con Claude:

1. Copia `.env.example` a `.env`.
2. Define tu clave en `ANTHROPIC_API_KEY` dentro de `.env`.
3. Reinicia la aplicación.

No compartas ni subas claves reales al repositorio.

## Estructura

```text
MediAlerta/
├── app.py             # Aplicación Streamlit
├── requirements.txt   # Dependencias Python
├── .env.example       # Plantilla para la clave opcional
├── .gitignore         # Excluye secretos y archivos locales
└── README.md          # Esta guía
```

## Arquitectura futura

La evolución propuesta para un sistema conectado contempla Flutter para la aplicación móvil, Flask para la API, Firebase Authentication y Firestore, FCM para notificaciones y ESP32/Adafruit IO para telemetría. Esos componentes todavía no están implementados en este prototipo.
