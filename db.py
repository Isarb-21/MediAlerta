"""SQLite persistence and demo seed data for MediAlerta."""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("MEDIALERTA_DB_PATH", ROOT / "data" / "medialerta_demo.db"))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the demo schema and seed it once. SQLite is included with Python."""
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'cuidador',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            condition TEXT NOT NULL DEFAULT '',
            caregiver_name TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            emergency_contact TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS vital_signs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            bpm REAL NOT NULL CHECK(bpm > 0 AND bpm <= 300),
            spo2 REAL NOT NULL CHECK(spo2 >= 0 AND spo2 <= 100),
            recorded_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'Simulación educativa'
        );
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            name TEXT NOT NULL,
            dose TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            compartment TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS medication_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL REFERENCES medications(id),
            scheduled_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Tomado','Pendiente','Olvidado')),
            recorded_at TEXT NOT NULL,
            UNIQUE(medication_id, scheduled_date)
        );
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL UNIQUE REFERENCES medications(id),
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            min_stock INTEGER NOT NULL DEFAULT 2 CHECK(min_stock >= 0),
            unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price >= 0)
        );
        CREATE TABLE IF NOT EXISTS carts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL REFERENCES users(username),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ordered')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cart_id INTEGER NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
            medication_id INTEGER NOT NULL REFERENCES medications(id),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL CHECK(unit_price >= 0),
            UNIQUE(cart_id, medication_id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            username TEXT NOT NULL,
            delivery_name TEXT NOT NULL,
            delivery_phone TEXT NOT NULL,
            delivery_address TEXT NOT NULL,
            payment_method TEXT NOT NULL CHECK(payment_method IN ('Efectivo contra entrega','Tarjeta (simulada)')),
            payment_status TEXT NOT NULL,
            order_status TEXT NOT NULL DEFAULT 'Confirmado (demo)',
            total REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            medication_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            subtotal REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            acknowledged INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_vitals_patient_time ON vital_signs(patient_id, recorded_at);
        CREATE INDEX IF NOT EXISTS idx_logs_date ON medication_logs(scheduled_date);
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(username, created_at);
        """)
        if db.execute("SELECT 1 FROM patients LIMIT 1").fetchone():
            return

        db.execute("INSERT INTO users(username, role) VALUES ('cuidador', 'cuidador')")
        patient_id = db.execute(
            "INSERT INTO patients(name, age, condition, caregiver_name, phone, emergency_contact) VALUES (?, ?, ?, ?, ?, ?)",
            ("Ana García", 72, "Datos ficticios para demostración educativa", "María López", "+57 311 234 5678", "Camilo García"),
        ).lastrowid
        user = "cuidador"
        medication_rows = [
            ("Losartán", "50 mg", "08:00", "A1", 12, 3, 12000.0),
            ("Metformina", "500 mg", "08:30", "B2", 9, 3, 9000.0),
            ("Atorvastatina", "20 mg", "20:00", "C1", 2, 4, 15000.0),
            ("Vitamina D", "1 cápsula", "21:00", "D3", 0, 3, 18000.0),
        ]
        medication_ids = []
        for name, dose, scheduled_time, compartment, stock, minimum, price in medication_rows:
            med_id = db.execute(
                "INSERT INTO medications(patient_id,name,dose,scheduled_time,compartment) VALUES (?,?,?,?,?)",
                (patient_id, name, dose, scheduled_time, compartment),
            ).lastrowid
            medication_ids.append(med_id)
            db.execute(
                "INSERT INTO inventory(medication_id,stock,min_stock,unit_price) VALUES (?,?,?,?)",
                (med_id, stock, minimum, price),
            )
        today = date.today().isoformat()
        for med_id, status in zip(medication_ids, ["Tomado", "Tomado", "Pendiente", "Olvidado"]):
            db.execute(
                "INSERT INTO medication_logs(medication_id,scheduled_date,status,recorded_at) VALUES (?,?,?,?)",
                (med_id, today, status, datetime.now().isoformat(timespec="seconds")),
            )
        # Seed a handful of today's simulated readings so average cards work immediately.
        now = datetime.now()
        samples = [(76, 98), (74, 97), (79, 98), (77, 97)]
        for offset, (bpm, spo2) in enumerate(samples):
            recorded = datetime.combine(now.date(), time(8 + offset * 2, 0)).isoformat(timespec="seconds")
            db.execute(
                "INSERT INTO vital_signs(patient_id,bpm,spo2,recorded_at,source) VALUES (?,?,?,?,?)",
                (patient_id, bpm, spo2, recorded, "Simulación educativa"),
            )
        cart_id = db.execute(
            "INSERT INTO carts(username,status,created_at) VALUES (?, 'active', ?)",
            (user, datetime.now().isoformat(timespec="seconds")),
        ).lastrowid
        # An empty cart is kept for the demo user and reused as needed.
        db.execute("UPDATE carts SET status='ordered' WHERE id=?", (cart_id,))


def get_patient() -> dict[str, Any]:
    with connect() as db:
        row = db.execute("SELECT * FROM patients ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else {}


def get_vitals(patient_id: int, days: int = 7) -> list[dict[str, Any]]:
    start = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM vital_signs WHERE patient_id=? AND recorded_at>=? ORDER BY recorded_at",
            (patient_id, start),
        ).fetchall()
        return [dict(row) for row in rows]


def add_vital(patient_id: int, bpm: float, spo2: float, source: str = "Simulación educativa") -> None:
    if not 1 <= float(bpm) <= 300 or not 0 <= float(spo2) <= 100:
        raise ValueError("BPM debe estar entre 1 y 300 y SpO₂ entre 0 y 100.")
    with connect() as db:
        db.execute(
            "INSERT INTO vital_signs(patient_id,bpm,spo2,recorded_at,source) VALUES (?,?,?,?,?)",
            (patient_id, float(bpm), float(spo2), datetime.now().isoformat(timespec="seconds"), source),
        )


def list_medications(patient_id: int, active_only: bool = True) -> list[dict[str, Any]]:
    query = """SELECT m.*, i.stock, i.min_stock, i.unit_price FROM medications m
               LEFT JOIN inventory i ON i.medication_id=m.id WHERE m.patient_id=?"""
    if active_only:
        query += " AND m.active=1"
    query += " ORDER BY m.scheduled_time, m.name"
    with connect() as db:
        return [dict(row) for row in db.execute(query, (patient_id,)).fetchall()]


def save_medication(patient_id: int, name: str, dose: str, scheduled_time: str, compartment: str, stock: int, min_stock: int, price: float, medication_id: int | None = None) -> None:
    datetime.strptime(scheduled_time, "%H:%M")
    if not name.strip() or not dose.strip() or stock < 0 or min_stock < 0 or price < 0:
        raise ValueError("Completa los datos y usa cantidades/precios no negativos.")
    with connect() as db:
        if medication_id:
            db.execute(
                "UPDATE medications SET name=?,dose=?,scheduled_time=?,compartment=?,active=1 WHERE id=? AND patient_id=?",
                (name.strip(), dose.strip(), scheduled_time, compartment.strip(), medication_id, patient_id),
            )
            db.execute(
                "INSERT INTO inventory(medication_id,stock,min_stock,unit_price) VALUES (?,?,?,?) ON CONFLICT(medication_id) DO UPDATE SET stock=excluded.stock,min_stock=excluded.min_stock,unit_price=excluded.unit_price",
                (medication_id, stock, min_stock, price),
            )
        else:
            med_id = db.execute(
                "INSERT INTO medications(patient_id,name,dose,scheduled_time,compartment) VALUES (?,?,?,?,?)",
                (patient_id, name.strip(), dose.strip(), scheduled_time, compartment.strip()),
            ).lastrowid
            db.execute("INSERT INTO inventory(medication_id,stock,min_stock,unit_price) VALUES (?,?,?,?)", (med_id, stock, min_stock, price))


def deactivate_medication(patient_id: int, medication_id: int) -> None:
    with connect() as db:
        db.execute("UPDATE medications SET active=0 WHERE id=? AND patient_id=?", (medication_id, patient_id))


def record_medication_status(medication_id: int, status: str, scheduled_date: str | None = None) -> None:
    day = scheduled_date or date.today().isoformat()
    with connect() as db:
        db.execute(
            "INSERT INTO medication_logs(medication_id,scheduled_date,status,recorded_at) VALUES (?,?,?,?) ON CONFLICT(medication_id,scheduled_date) DO UPDATE SET status=excluded.status,recorded_at=excluded.recorded_at",
            (medication_id, day, status, datetime.now().isoformat(timespec="seconds")),
        )


def get_medication_logs(patient_id: int, day: str | None = None) -> list[dict[str, Any]]:
    day = day or date.today().isoformat()
    with connect() as db:
        rows = db.execute(
            "SELECT l.*,m.name,m.dose,m.scheduled_time FROM medication_logs l JOIN medications m ON m.id=l.medication_id WHERE m.patient_id=? AND l.scheduled_date=? ORDER BY m.scheduled_time",
            (patient_id, day),
        ).fetchall()
        return [dict(row) for row in rows]


def get_history(patient_id: int, limit: int = 100) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            "SELECT l.scheduled_date,l.status,l.recorded_at,m.name,m.dose,m.scheduled_time FROM medication_logs l JOIN medications m ON m.id=l.medication_id WHERE m.patient_id=? ORDER BY l.scheduled_date DESC,m.scheduled_time LIMIT ?",
            (patient_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def get_inventory(patient_id: int) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            "SELECT m.id AS medication_id,m.name,m.compartment,i.stock,i.min_stock,i.unit_price FROM medications m JOIN inventory i ON i.medication_id=m.id WHERE m.patient_id=? AND m.active=1 ORDER BY m.compartment",
            (patient_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_active_cart(username: str) -> int:
    with connect() as db:
        row = db.execute("SELECT id FROM carts WHERE username=? AND status='active' ORDER BY id DESC LIMIT 1", (username,)).fetchone()
        if row:
            return int(row["id"])
        cur = db.execute("INSERT INTO carts(username,status,created_at) VALUES (?, 'active', ?)", (username, datetime.now().isoformat(timespec="seconds")))
        return int(cur.lastrowid)


def get_cart(cart_id: int) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            "SELECT ci.id,ci.medication_id,ci.quantity,ci.unit_price,m.name,m.dose,m.compartment,(ci.quantity*ci.unit_price) AS subtotal FROM cart_items ci JOIN medications m ON m.id=ci.medication_id WHERE ci.cart_id=? ORDER BY m.name",
            (cart_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def add_cart_item(cart_id: int, medication_id: int, quantity: int) -> None:
    if quantity <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")
    with connect() as db:
        item = db.execute(
            "SELECT i.unit_price,m.active FROM inventory i JOIN medications m ON m.id=i.medication_id WHERE i.medication_id=?",
            (medication_id,),
        ).fetchone()
        if not item or not item["active"]:
            raise ValueError("El producto no está disponible en el catálogo demo.")
        db.execute(
            "INSERT INTO cart_items(cart_id,medication_id,quantity,unit_price) VALUES (?,?,?,?) ON CONFLICT(cart_id,medication_id) DO UPDATE SET quantity=excluded.quantity,unit_price=excluded.unit_price",
            (cart_id, medication_id, quantity, item["unit_price"]),
        )


def remove_cart_item(cart_item_id: int, cart_id: int) -> None:
    with connect() as db:
        db.execute("DELETE FROM cart_items WHERE id=? AND cart_id=?", (cart_item_id, cart_id))


def create_order(cart_id: int, username: str, patient_id: int, delivery_name: str, delivery_phone: str, delivery_address: str, payment_method: str) -> int:
    if payment_method not in {"Efectivo contra entrega", "Tarjeta (simulada)"}:
        raise ValueError("Método de pago no válido.")
    items = get_cart(cart_id)
    if not items:
        raise ValueError("El carrito está vacío.")
    if not delivery_name.strip() or not delivery_phone.strip() or not delivery_address.strip():
        raise ValueError("Completa nombre, teléfono y dirección de entrega.")
    total = sum(float(item["subtotal"]) for item in items)
    payment_status = "Pendiente contra entrega" if payment_method == "Efectivo contra entrega" else "Aprobado (simulación educativa)"
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        order_id = db.execute(
            "INSERT INTO orders(patient_id,username,delivery_name,delivery_phone,delivery_address,payment_method,payment_status,order_status,total,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (patient_id, username, delivery_name.strip(), delivery_phone.strip(), delivery_address.strip(), payment_method, payment_status, "Confirmado (demo)", total, now),
        ).lastrowid
        for item in items:
            db.execute(
                "INSERT INTO order_items(order_id,medication_name,quantity,unit_price,subtotal) VALUES (?,?,?,?,?)",
                (order_id, item["name"], item["quantity"], item["unit_price"], item["subtotal"]),
            )
        db.execute("DELETE FROM cart_items WHERE cart_id=?", (cart_id,))
        db.execute("UPDATE carts SET status='ordered' WHERE id=?", (cart_id,))
    return int(order_id)


def get_orders(username: str, limit: int = 20) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("SELECT * FROM orders WHERE username=? ORDER BY created_at DESC LIMIT ?", (username, limit)).fetchall()
        result = []
        for row in rows:
            order = dict(row)
            order["items"] = [dict(item) for item in db.execute("SELECT * FROM order_items WHERE order_id=?", (order["id"],)).fetchall()]
            result.append(order)
        return result


def get_dashboard_summary(patient_id: int) -> dict[str, Any]:
    today = date.today().isoformat()
    with connect() as db:
        averages = db.execute(
            "SELECT AVG(bpm) AS avg_bpm,AVG(spo2) AS avg_spo2,COUNT(*) AS count FROM vital_signs WHERE patient_id=? AND date(recorded_at)=?",
            (patient_id, today),
        ).fetchone()
        total_meds = db.execute("SELECT COUNT(*) AS n FROM medications WHERE patient_id=? AND active=1", (patient_id,)).fetchone()["n"]
        taken = db.execute("SELECT COUNT(*) AS n FROM medication_logs l JOIN medications m ON m.id=l.medication_id WHERE m.patient_id=? AND m.active=1 AND l.scheduled_date=? AND l.status='Tomado'", (patient_id, today)).fetchone()["n"]
        latest = db.execute("SELECT recorded_at FROM vital_signs WHERE patient_id=? ORDER BY recorded_at DESC LIMIT 1", (patient_id,)).fetchone()
    adherence = round((taken / total_meds) * 100) if total_meds else 0
    return {
        "avg_bpm": round(averages["avg_bpm"], 1) if averages["avg_bpm"] is not None else None,
        "avg_spo2": round(averages["avg_spo2"], 1) if averages["avg_spo2"] is not None else None,
        "readings_count": averages["count"],
        "adherence": adherence,
        "latest": latest["recorded_at"] if latest else None,
        "date": today,
    }


def build_demo_alerts(patient_id: int) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    summary = get_dashboard_summary(patient_id)
    if summary["avg_bpm"] is not None and (summary["avg_bpm"] < 60 or summary["avg_bpm"] > 100):
        alerts.append({"type": "Biomédica", "severity": "Alta", "message": f"El promedio diario registrado de BPM es {summary['avg_bpm']}. Verifica la medición y consulta al profesional responsable si hay síntomas."})
    if summary["avg_spo2"] is not None and summary["avg_spo2"] < 95:
        alerts.append({"type": "Biomédica", "severity": "Alta", "message": f"El promedio diario registrado de SpO₂ es {summary['avg_spo2']}%. Verifica el sensor y contacta al profesional responsable si hay preocupación."})
    for log in get_medication_logs(patient_id):
        if log["status"] == "Olvidado":
            alerts.append({"type": "Medicación", "severity": "Media", "message": f"{log['name']} figura como dosis olvidada hoy ({log['scheduled_time']}). Revisa el registro; no administres dosis extra por indicación de la app."})
    for item in get_inventory(patient_id):
        if item["stock"] <= item["min_stock"]:
            alerts.append({"type": "Inventario", "severity": "Media", "message": f"Inventario bajo: {item['name']} tiene {item['stock']} unidades en el compartimento {item['compartment']}."})
    return alerts
