# MediAlerta — MVP conectado

Prototipo web para MediAlerta, implementado con Python y Streamlit. Lee BPM y oxigenación desde Adafruit IO, y campos de alerta desde SheetDB cuando está configurado.

> **Importante:** no se muestran datos de paciente, medicamentos, adherencia, inventario ni lecturas históricas si las fuentes conectadas no los entregan. La aplicación no controla el ESP32 ni sustituye la atención de profesionales de salud. El inicio de sesión sigue siendo solo de demostración.

## Requisitos

- Python 3.10 o superior
- pip

## Instalación y ejecución

### Windows (PowerShell)

Abre PowerShell en la carpeta del proyecto y ejecuta:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

No es necesario activar el entorno virtual; usar su `python.exe` directamente evita instalar las dependencias en otro Python. Si prefieres activarlo:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Si PowerShell bloquea la activación del entorno, puedes omitirla y ejecutar los comandos con `.\.venv\Scripts\python.exe`, como en el ejemplo anterior. Para permitir scripts de activación para tu usuario actual:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Si `py` no está disponible, sustituye `py -3` por `python` al crear el entorno. En VS Code, selecciona `.venv\Scripts\python.exe` como intérprete para que el editor detecte las mismas librerías.

### macOS/Linux

Desde la carpeta `MediAlerta`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Abre en el navegador la dirección que indique Streamlit (normalmente `http://localhost:8501`). En el inicio de sesión de demo, ingresa cualquier usuario y contraseña no vacíos.

## Configuración del agente

El agente usa reglas locales si no configuras una clave de Anthropic. Adafruit IO es necesaria para consultar datos y no se usan valores de ejemplo cuando la fuente no está configurada:

1. Copia `.env.example` a `.env` (en PowerShell: `Copy-Item .env.example .env`).
2. Configura `ANTHROPIC_API_KEY` si deseas generación con Claude.
3. Configura `ADAFRUIT_IO_USERNAME` y `ADAFRUIT_IO_KEY`. Los feeds predeterminados son `bpm` y `oxigenacion`; puedes cambiarlos con `ADAFRUIT_IO_BPM_FEED` y `ADAFRUIT_IO_SPO2_FEED`.
4. Los avisos deterministas usan `ALERTA_BPM_MIN=60`, `ALERTA_BPM_MAX=100` y `ALERTA_SPO2_MIN=95` por defecto. Ajusta estos valores en `.env` solo según los límites acordados con el equipo de salud.
5. Opcionalmente, define `SHEETDB_API_URL` para leer el estado de pastillero del último registro.
6. Reinicia Streamlit.

La aplicación y el agente leen Adafruit IO y SheetDB en modo de solo lectura; no se conectan directamente al ESP32 ni controlan el motor. Los avisos de Telegram siguen a cargo del firmware. Si faltan credenciales o una fuente falla, se muestra un error en lugar de sustituir las lecturas con valores inventados. Actualmente Adafruit IO entrega la última lectura de BPM y oxigenación; SheetDB puede entregar los campos de alerta disponibles. Historial, medicamentos, adherencia, inventario y perfil requieren que se conecte una fuente que los registre.

Al habilitar Claude, el contexto consultado se envía a Anthropic para generar la respuesta. Configura secretos solo en `.env`; no compartas ni subas claves reales al repositorio. Rota cualquier clave o token que se haya expuesto.

## Estructura

```text
MediAlerta/
├── app.py             # Aplicación Streamlit
├── requirements.txt   # Dependencias Python
├── .env.example       # Plantilla de configuración local del agente
├── .gitignore         # Excluye secretos y archivos locales
└── README.md          # Esta guía
```

## Arquitectura futura

El dashboard muestra datos leídos de Adafruit IO y SheetDB; MediAlerta no está conectado a Firebase ni a servicios de emergencia. El firmware gestiona sus propias alertas de Telegram.
