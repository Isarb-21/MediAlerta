# MediAlerta — MVP para cuidadores

Aplicación demostrativa en Streamlit para presentar lecturas de BPM y SpO₂ desde Adafruit IO, consultar alertas del pastillero (SheetDB opcional), usar un agente de apoyo y organizar una lista de reposición.

> El hardware no mide temperatura: MediAlerta no presenta ese dato. Esta aplicación no diagnostica, no sustituye a profesionales y no debe usarse para decisiones clínicas. El agente de compras organiza únicamente los productos que registra el cuidador; no elige ni prescribe medicamentos, no realiza pedidos ni procesa pagos.

## Ejecutar

Requiere Python 3.10+:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

En macOS/Linux, activa `.venv` con `source .venv/bin/activate`, luego instala dependencias y ejecuta `python -m streamlit run app.py`.

## Configuración

Copia `.env.example` como `.env` y completa las credenciales de Adafruit IO y los feeds de BPM y oxigenación. `ANTHROPIC_API_KEY` es opcional; sin esa clave, el agente de cuidado usa respuestas locales y el agente de compras aplica comparación determinista del stock.

No publiques claves API. El inicio de sesión actual es solo demostrativo.

## Páginas

- **Dashboard:** lecturas disponibles de Adafruit IO; si no hay conexión, muestra el error en vez de fabricar datos. Temperatura no aparece.
- **Asistente de cuidado:** usa el agente LangGraph existente, reglas de alertas y contexto de lecturas conectadas.
- **Carrito de compras:** el cuidador ingresa el producto, stock, mínimo y cantidad deseada. El agente identifica artículos que alcanzan el mínimo, crea una lista y ofrece enlaces de búsqueda a la tienda elegida. El usuario verifica el artículo y completa cualquier compra en la página del comercio.

El carrito se guarda únicamente en la sesión actual de Streamlit. No hay integración de pago, órdenes automáticas ni conexión con una farmacia.
