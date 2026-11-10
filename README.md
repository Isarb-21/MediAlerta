# MediAlerta — MVP educativo con persistencia local

Demo educativa construida con Streamlit y SQLite. Incluye dashboard con promedios diarios de BPM/SpO₂, configuración de medicamentos, registro de adherencia, alertas derivadas de reglas sencillas, inventario, carrito y pedidos demo.

> **Alcance y seguridad:** todos los datos iniciales son ficticios y se guardan localmente en `data/medialerta_demo.db`. No se maneja temperatura. La demo no es un sistema clínico, no diagnostica ni recomienda tratamientos. El catálogo/precios y pedidos son simulados. El pago con tarjeta se representa únicamente como simulación: no solicites ni almacenes número, vencimiento o CVV. Para pagos reales se requiere un proveedor de pago seguro; esta app no procesa dinero. El inicio de sesión es solo demostrativo.

## Ejecutar

Requiere Python 3.10+:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

En macOS/Linux, activa `.venv` con `source .venv/bin/activate`, luego instala dependencias con `python -m pip install -r requirements.txt` y ejecuta `streamlit run app.py`.

No se necesita Firebase, Anthropic ni un dispositivo para ejecutar la demo. SQLite forma parte de Python. La base se crea y se siembra automáticamente al iniciar.

## Datos de acceso de demo

Ingresa cualquier nombre de usuario y contraseña no vacíos. Los datos pertenecen al paciente de demostración y son persistentes en SQLite. Para reiniciar el escenario, detén Streamlit y elimina `data/medialerta_demo.db`; la aplicación lo vuelve a crear con datos iniciales ficticios.

## Módulos

- **Dashboard:** promedio diario de BPM y SpO₂ calculado desde registros del día, adherencia de dosis registrada, número de lecturas, tendencia semanal, alertas y formulario para agregar lecturas simuladas. El periodo y el conteo se muestran junto a los promedios.
- **Medicamentos:** agregar, editar y desactivar medicamentos, programar horarios en formato 24 h, ajustar inventario/precios demo y registrar estado de dosis.
- **Asistente de cuidado:** consulta el contexto SQLite con el agente existente. `ANTHROPIC_API_KEY` es opcional; sin clave responde con reglas locales.
- **Carrito y pedidos:** el agente de compras revisa el mínimo configurado del inventario y propone reabastecer solamente productos ya configurados. Permite revisar el carrito, ingresar datos de entrega no sensibles, elegir efectivo contra entrega o tarjeta simulada y guardar pedidos en SQLite.
- **Persistencia:** pacientes, lecturas, medicamentos, logs de dosis, inventario, carrito y órdenes se guardan localmente.

## Configuración opcional de IA

Copia `.env.example` a `.env` y define `ANTHROPIC_API_KEY` si se quiere usar Claude para el asistente de cuidado. Las funciones principales, reglas y agente de reabastecimiento funcionan sin esa clave. No subas secretos.

## Esquema SQLite

`users`, `patients`, `vital_signs`, `medications`, `medication_logs`, `inventory`, `carts`, `cart_items`, `orders`, `order_items` y `alerts`. La base se excluye del control de versiones.

## Limitaciones

Los promedios y umbrales son de demostración y no deben interpretarse clínicamente. El carrito organiza una orden educativa; no reserva stock real, no está conectado a una farmacia ni a un proveedor de entrega. La tarjeta nunca se captura. La autenticación es simulada y no protege información sensible; no uses datos reales de pacientes.
