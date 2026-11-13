# ==========================================================
#  PASTILLERO - MicroPython (ESP32)
#  Pines iguales al codigo de Arduino
# ==========================================================
import time, math, json
import network, ntptime
from machine import Pin, I2C, PWM, time_pulse_us

try:
    import urequests as requests
except ImportError:
    import requests

# ---------------- RED Y SERVICIOS ----------------
WIFI_SSID = "yomellamopablo"
WIFI_PASS = "salchipapa123456789"
TELEGRAM_TOKEN = "9134172375:AAGFleW3JhOytfMqQGnpJC3zfAr1BjTwEPM"
TELEGRAM_CHAT_ID = "7912478824"
SHEETDB_URL = "https://sheetdb.io/api/v1/fyz0e3drzv0bv"
AIO_USER = "teawen"
AIO_KEY = "aio_axXu00FXSfDVST3WOATxNCtCoHxA"

GMT_OFFSET_SEC = -18000                 # Colombia (UTC-5)
TIEMPO_SIN_PRESENCIA_MS = 300000        # 5 min
TIEMPO_SIN_CONFIRMAR_MS = 120000        # 2 min

# ---------------- GIRO DEL PASTILLERO ----------------
GRADOS_POR_GIRO = 25.71
PASTILLAS_POR_VUELTA = 14
PASOS_POR_REVOLUCION = 4096

# ---------------- PINES ----------------
PIN_BUZZER = 15
PIN_TRIG, PIN_ECHO = 5, 23
IN_PINS = (16, 17, 18, 19)
PIN_SERVO = 4
SDA, SCL = 21, 22
FILAS_PINS = (13, 12, 14, 27)
COLS_PINS = (26, 25, 33, 32)

# ---------------- PARAMETROS ----------------
DISTANCIA_MIN_CM, DISTANCIA_MAX_CM = 2.0, 20.0
LECTURAS_NECESARIAS = 5
ANGULO_CERRADO, ANGULO_ABIERTO = 0, 90
TIEMPO_ABIERTO_MS = 5000
US_MIN, US_MAX = 500, 2500

UMBRAL_DEDO = 20000
DURACION_MEDICION_MS = 15000
ESPERA_ESTAB_MS = 3000
TIEMPO_RESULTADO_MS = 6000
VENTANA_SPO2 = 50
MAX_LATIDOS = 100

NUM_DIAS = 7
NOMBRES_DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]

KEYS = (("1", "2", "3", "A"),
        ("4", "5", "6", "B"),
        ("7", "8", "9", "C"),
        ("*", "0", "#", "D"))

# ---------------- ESTADOS Y FASES ----------------
(PEDIR_DIA, PEDIR_HORA_ACTUAL, PEDIR_AMPMS_ACTUAL, PEDIR_CANTIDAD,
 PEDIR_CONFIRMAR_CANTIDAD, PEDIR_HORA_PASTA, PEDIR_AMPM_PASTA, RELOJ_EN_VIVO,
 AJUSTAR_DIA, AJUSTAR_INDICE, AJUSTAR_HORA, AJUSTAR_AMPM, AJUSTAR_RELOJ_HORA,
 AJUSTAR_RELOJ_AMPM, AJUSTAR_AGREGAR_HORA, AJUSTAR_AGREGAR_AMPM,
 AJUSTAR_BORRAR) = range(17)

(FASE_NINGUNA, FASE_ALARMA, FASE_PEDIR_DEDO, FASE_MIDIENDO, FASE_RESULTADO,
 FASE_CONFIRMAR, FASE_DISPENSANDO) = range(7)


# ==========================================================
#  DRIVER LCD I2C (PCF8574) 20x4
# ==========================================================
class LCD:
    def __init__(self, i2c, addr=0x27, cols=20, rows=4):
        self.i2c, self.addr = i2c, addr
        self.bl = 0x08
        self.offs = (0x00, 0x40, 0x14, 0x54)
        time.sleep_ms(50)
        for _ in range(3):
            self._send4(0x30, 0)
            time.sleep_ms(5)
        self._send4(0x20, 0)
        self._cmd(0x28)
        self._cmd(0x0C)
        self._cmd(0x06)
        self.clear()

    def _w(self, b):
        self.i2c.writeto(self.addr, bytes([b | self.bl]))

    def _send4(self, n, rs):
        b = (n & 0xF0) | rs
        self._w(b | 0x04)
        time.sleep_us(2)
        self._w(b & ~0x04)
        time.sleep_us(60)

    def _cmd(self, c):
        self._send4(c, 0)
        self._send4(c << 4, 0)

    def _char(self, c):
        self._send4(c, 1)
        self._send4(c << 4, 1)

    def clear(self):
        self._cmd(0x01)
        time.sleep_ms(3)

    def puts(self, col, row, s):
        self._cmd(0x80 | (col + self.offs[row]))
        for ch in s:
            self._char(ord(ch) & 0xFF)


# ==========================================================
#  DRIVER MAX30102 (minimo)
# ==========================================================
class MAX30102:
    ADDR = 0x57

    def __init__(self, i2c):
        self.i2c = i2c
        if self.i2c.readfrom_mem(self.ADDR, 0xFF, 1)[0] != 0x15:
            raise OSError("MAX30102 no responde")
        self.i2c.writeto_mem(self.ADDR, 0x09, b"\x40")      # reset
        time.sleep_ms(100)
        self.i2c.writeto_mem(self.ADDR, 0x08, b"\x50")      # avg 4, rollover
        self.i2c.writeto_mem(self.ADDR, 0x09, b"\x03")      # modo SpO2 (rojo+IR)
        # rango 4096, 400 muestras/s, pulso 411us  (400/4 = 100 muestras/s)
        self.i2c.writeto_mem(self.ADDR, 0x0A, b"\x2F")
        self.i2c.writeto_mem(self.ADDR, 0x0C, bytes([20]))  # LED rojo
        self.i2c.writeto_mem(self.ADDR, 0x0D, bytes([20]))  # LED IR
        self.clear_fifo()

    def clear_fifo(self):
        for r in (0x04, 0x05, 0x06):
            self.i2c.writeto_mem(self.ADDR, r, b"\x00")

    def leer(self):
        """Devuelve lista de (rojo, ir) con las muestras nuevas."""
        wr = self.i2c.readfrom_mem(self.ADDR, 0x04, 1)[0]
        rd = self.i2c.readfrom_mem(self.ADDR, 0x06, 1)[0]
        n = (wr - rd) & 0x1F
        if n == 0:
            return []
        d = self.i2c.readfrom_mem(self.ADDR, 0x07, n * 6)
        out = []
        for i in range(n):
            o = i * 6
            red = ((d[o] << 16) | (d[o + 1] << 8) | d[o + 2]) & 0x3FFFF
            ir = ((d[o + 3] << 16) | (d[o + 4] << 8) | d[o + 5]) & 0x3FFFF
            out.append((red, ir))
        return out


# ==========================================================
#  HARDWARE
# ==========================================================
i2c = I2C(0, sda=Pin(SDA), scl=Pin(SCL), freq=100000)
lcd = LCD(i2c)

buzzer = Pin(PIN_BUZZER, Pin.OUT)
trig = Pin(PIN_TRIG, Pin.OUT)
echo = Pin(PIN_ECHO, Pin.IN, Pin.PULL_DOWN)
trig.value(0)
motor = [Pin(p, Pin.OUT) for p in IN_PINS]
servo = PWM(Pin(PIN_SERVO), freq=50)
filas = [Pin(p, Pin.OUT, value=0) for p in FILAS_PINS]
cols = [Pin(p, Pin.IN, Pin.PULL_DOWN) for p in COLS_PINS]

SECUENCIA_MOTOR = ((1, 0, 0, 0), (1, 1, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0),
                   (0, 0, 1, 0), (0, 0, 1, 1), (0, 0, 0, 1), (1, 0, 0, 1))

sensor = None
sensor_ok = False
wlan = network.WLAN(network.STA_IF)


# ==========================================================
#  ESTADO GLOBAL
# ==========================================================
class G:
    estado = PEDIR_DIA
    fase = FASE_NINGUNA
    ejecutar_giro = False
    pastillas_dispensadas = 0

    dia_actual, hora_actual, minuto_actual, segundo_actual = 0, 5, 17, 0
    periodo_actual = "PM"
    reloj_activo = False
    mostrando_fin_semana = False
    t_reloj = 0

    horarios = [[] for _ in range(NUM_DIAS)]    # cada uno: [hora, minuto, es_pm]
    dia_config = hora_config = cantidad_objetivo = 0
    tmp_hora = tmp_min = tmp_cantidad = 0
    dia_ajuste = idx_ajuste = 0
    input_temp = ""

    inicio_dispensado = ultima_medida = lecturas_cerca = 0
    inicio_fase_alerta = 0
    alerta_enviada = False
    fase_ant = FASE_NINGUNA

    inicio_medicion = ultimo_dedo = inicio_resultado = 0
    ultimo_print = 0
    lento = suave = prev_suave = prev_prev_suave = amplitud = 0.0
    ultimo_latido = 0
    bpm_lista = []
    s_red = s_ir = s_red2 = s_ir2 = 0.0
    n_muestras = 0
    suma_spo2 = 0.0
    n_ventanas = 0
    resultado_bpm = resultado_spo2 = 0

    ntp_ok = False
    wifi_estaba = True


def ms():
    return time.ticks_ms()


def dt(desde):
    return time.ticks_diff(time.ticks_ms(), desde)


# ==========================================================
#  UTILIDADES DE TEXTO Y PANTALLA
# ==========================================================
def dos(n):
    return "0%d" % n if n < 10 else str(n)


def pad(s):
    return (s + " " * 20)[:20]


def centrar(s):
    return pad(" " * ((20 - len(s)) // 2) + s)


def texto_horario(h, m, pm):
    return "%d:%s %s" % (h, dos(m), "PM" if pm else "AM")


def linea(fila, s):
    lcd.puts(0, fila, pad(s))


def pantalla(a="", b="", c="", d=""):
    lcd.clear()
    for i, s in enumerate((a, b, c, d)):
        if s:
            lcd.puts(0, i, s[:20])


def pantalla_hora(a, b):
    pantalla(a, b, "Hora: _:__", "#=OK  *=Borrar")


def cab_config():
    return "%s %d/%d" % (NOMBRES_DIAS[G.dia_config], G.hora_config + 1, G.cantidad_objetivo)


def cab_ajuste():
    return "%s #%d" % (NOMBRES_DIAS[G.dia_ajuste], G.idx_ajuste + 1)


def mostrar_entrada_cantidad():
    lcd.puts(10, 2, (G.input_temp or "_") + "      ")


def mostrar_entrada_hora():
    n = len(G.input_temp)
    h = "_" if n == 0 else (G.input_temp if n < 3 else G.input_temp[:n - 2])
    m = ("_" if n == 2 else "__") if n < 3 else G.input_temp[n - 2:]
    lcd.puts(6, 2, h + ":" + m + "      ")


def mostrar_entrada_indice():
    s = "Num: " + (G.input_temp or "_")
    n = int(G.input_temp) if G.input_temp else 0
    lst = G.horarios[G.dia_ajuste]
    if 1 <= n <= len(lst):
        h = lst[n - 1]
        s += " " + texto_horario(h[0], h[1], h[2])
    linea(2, s)


def mostrar_pantalla_dia():
    aj = (G.estado == AJUSTAR_DIA)
    titulo = "Ajustar cual dia?" if aj else "Que dia es hoy?"
    if not G.mostrando_fin_semana:
        pantalla(titulo, "1.Lunes  2.Martes", "3.Mier 4.Jue 5.Vie",
                 "1-5 C=Sab/Dom *=Sal" if aj else "Pulsa 1-5, C=Sab/Dom")
    else:
        pantalla(titulo, "6.Sabado 7.Domingo", "8.Cambiar hora" if aj else "",
                 "6-7 C=volver *=Salir" if aj else "Pulsa 6-7, C=volver")


def mostrar_pantalla():
    e = G.estado
    nueva = "Hora nueva: %d:%s" % (G.tmp_hora, dos(G.tmp_min))
    if e in (PEDIR_DIA, AJUSTAR_DIA):
        mostrar_pantalla_dia()
    elif e == PEDIR_HORA_ACTUAL:
        pantalla_hora("Hora del " + NOMBRES_DIAS[G.dia_actual], "Escribe la hora:")
    elif e == PEDIR_AMPMS_ACTUAL:
        pantalla("Es AM o PM?", "[A] -> AM", "[B] -> PM")
    elif e == PEDIR_CANTIDAD:
        pantalla("Dia: " + NOMBRES_DIAS[G.dia_config], "Cuantos horarios?",
                 "Cantidad: _", "#=OK  *=Borrar")
    elif e == PEDIR_CONFIRMAR_CANTIDAD:
        pantalla("Dia: " + NOMBRES_DIAS[G.dia_config],
                 "Sin horarios?" if G.cantidad_objetivo == 0
                 else "Son %d horarios?" % G.cantidad_objetivo,
                 "Estas seguro?", "[A]=Si  [B]=No")
    elif e == PEDIR_HORA_PASTA:
        pantalla_hora(cab_config(), "Hora de la pasta:")
    elif e == PEDIR_AMPM_PASTA:
        pantalla(cab_config(), "Es AM o PM?", "[A] -> AM", "[B] -> PM")
    elif e == RELOJ_EN_VIVO:
        lcd.clear()
        actualizar_reloj_en_pantalla()
    elif e == AJUSTAR_INDICE:
        pantalla("Ajustar " + NOMBRES_DIAS[G.dia_ajuste],
                 "Hay %d horarios #=OK" % len(G.horarios[G.dia_ajuste]),
                 "", "A=Agregar B=Quitar")
        mostrar_entrada_indice()
    elif e == AJUSTAR_HORA:
        h = G.horarios[G.dia_ajuste][G.idx_ajuste]
        pantalla_hora(cab_ajuste(), "Actual: " + texto_horario(h[0], h[1], h[2]))
    elif e == AJUSTAR_AMPM:
        pantalla(cab_ajuste(), nueva, "[A]=AM  [B]=PM", "*=Atras")
    elif e == AJUSTAR_RELOJ_HORA:
        pantalla_hora("Cambiar hora actual", "Hoy es " + NOMBRES_DIAS[G.dia_actual])
    elif e == AJUSTAR_RELOJ_AMPM:
        pantalla("Cambiar hora actual", nueva, "[A]=AM  [B]=PM", "*=Atras")
    elif e == AJUSTAR_AGREGAR_HORA:
        pantalla_hora("Agregar " + NOMBRES_DIAS[G.dia_ajuste], "Hora de la pasta:")
    elif e == AJUSTAR_AGREGAR_AMPM:
        pantalla("Agregar " + NOMBRES_DIAS[G.dia_ajuste],
                 "Hora: %d:%s" % (G.tmp_hora, dos(G.tmp_min)), "[A]=AM  [B]=PM", "*=Atras")
    elif e == AJUSTAR_BORRAR:
        pantalla("Quitar en " + NOMBRES_DIAS[G.dia_ajuste], "Cual horario borrar?",
                 "", "#=OK *=Borrar/Atras")
        mostrar_entrada_indice()


# ==========================================================
#  WIFI, TELEGRAM, SHEETDB, ADAFRUIT
# ==========================================================
def http_post(url, datos, headers=None):
    headers = headers or {}
    headers["Content-Type"] = "application/json"
    try:
        try:
            r = requests.post(url, data=json.dumps(datos), headers=headers, timeout=6)
        except TypeError:                       # versiones sin parametro timeout
            r = requests.post(url, data=json.dumps(datos), headers=headers)
        codigo = r.status_code
        r.close()
        return codigo
    except Exception as ex:
        print("HTTP error:", ex)
        return -1


def hay_wifi():
    ok = wlan.isconnected()
    if ok and not G.wifi_estaba:
        print("WiFi reconectado.")
    if not ok and G.wifi_estaba:
        print("WiFi perdido. Reintentando...")
        try:
            wlan.connect(WIFI_SSID, WIFI_PASS)
        except Exception:
            pass
    G.wifi_estaba = ok
    return ok


def fecha_hora():
    if G.ntp_ok:
        t = time.localtime(time.time() + GMT_OFFSET_SEC)
        return "%04d-%02d-%02d %02d:%02d:%02d" % t[:6]
    return "%s %d:%s %s" % (NOMBRES_DIAS[G.dia_actual], G.hora_actual,
                            dos(G.minuto_actual), G.periodo_actual)


def enviar_telegram(mensaje):
    if not hay_wifi():
        return
    url = "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_TOKEN
    c = http_post(url, {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje})
    print("Telegram HTTP Code:", c)


def enviar_sheetdb(hora, ultra, tecla, pt_lleno, bpm="--", spo2="--"):
    if not hay_wifi():
        print("SheetDB: sin WiFi")
        return
    fila = {"DIA": NOMBRES_DIAS[G.dia_actual], "HORA PST": hora,
            "ALERTA ULT": ultra, "ALERTA TCD": tecla, "ALERTA PST VACIO": pt_lleno}
    # Si tu hoja tiene columnas BPM y SPO2, descomenta estas dos lineas:
    # fila["BPM"] = bpm; fila["SPO2"] = spo2
    c = http_post(SHEETDB_URL, {"data": [fila]})
    print("SheetDB HTTP Code:", c)


def enviar_adafruit(feed, valor):
    if not hay_wifi():
        return
    url = "https://io.adafruit.com/api/v2/%s/feeds/%s/data" % (AIO_USER, feed)
    c = http_post(url, {"value": valor}, {"X-AIO-Key": AIO_KEY})
    print("Adafruit HTTP Code (%s): %s" % (feed, c))


def reportar_medicion():
    ts = fecha_hora()
    if G.resultado_bpm > 0:
        enviar_adafruit("bpm", G.resultado_bpm)
        if G.resultado_bpm < 60 or G.resultado_bpm > 100:
            enviar_telegram("ALERTA: pulsaciones fuera de rango: %d BPM (%s)." % (G.resultado_bpm, ts))
    if G.resultado_spo2 > 0:
        enviar_adafruit("oxigenacion", G.resultado_spo2)
        if G.resultado_spo2 < 90:
            enviar_telegram("ALERTA: oxigenacion baja: %d%% (%s)." % (G.resultado_spo2, ts))


def registrar_toma():
    ts = fecha_hora()
    enviar_sheetdb(ts, "OK", "OK", "OK",
                   str(G.resultado_bpm) if G.resultado_bpm > 0 else "--",
                   str(G.resultado_spo2) if G.resultado_spo2 > 0 else "--")
    enviar_telegram("Pasta tomada a las %s." % ts)


def revisar_alertas():
    if G.fase != G.fase_ant:
        G.fase_ant = G.fase
        G.inicio_fase_alerta = ms()
        G.alerta_enviada = False
    if G.alerta_enviada:
        return
    if G.fase == FASE_ALARMA and dt(G.inicio_fase_alerta) >= TIEMPO_SIN_PRESENCIA_MS:
        G.alerta_enviada = True
        ts = fecha_hora()
        enviar_telegram("ALERTA: pasaron mas de 5 minutos sin movimiento frente al pastillero (%s)." % ts)
        enviar_sheetdb(ts, "Alerta: sin movimiento > 5 min", "OK", "OK")
    if G.fase == FASE_CONFIRMAR and dt(G.inicio_fase_alerta) >= TIEMPO_SIN_CONFIRMAR_MS:
        G.alerta_enviada = True
        ts = fecha_hora()
        enviar_telegram("ADVERTENCIA: presencia detectada pero no se confirmo con # (%s)." % ts)
        enviar_sheetdb(ts, "OK", "Alerta: sin confirmacion en teclado", "OK")


def conectar_wifi():
    pantalla("", centrar("Conectando WiFi"))
    print("Conectando a WiFi...")
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    t0 = ms()
    puntos = 0
    while not wlan.isconnected() and dt(t0) < 10000:
        time.sleep_ms(500)
        puntos = (puntos + 1) % 4
        linea(2, centrar("." * puntos))

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print("WiFi conectado exitosamente. IP:", ip)
        pantalla("", centrar("WiFi conectado!"), centrar(ip))
        time.sleep_ms(2000)
        try:
            ntptime.settime()
            G.ntp_ok = True
        except Exception as ex:
            print("NTP fallo:", ex)

        print("=== PRUEBA DE SERVICIOS ===")
        enviar_telegram("Pastillero conectado exitosamente.")
        enviar_sheetdb("PRUEBA INICIO", "OK", "OK", "OK")
        print("=== FIN PRUEBA ===")
    else:
        print("Sin WiFi: el pastillero funciona, pero no enviara datos.")
        pantalla("", centrar("Sin WiFi"), centrar("Modo sin conexion"))
        time.sleep_ms(2500)


# ==========================================================
#  MEDICION DE PULSO Y SpO2
# ==========================================================
def resetear_medicion():
    G.bpm_lista = []
    G.ultimo_latido = 0
    G.amplitud = 0.0
    G.s_red = G.s_ir = G.s_red2 = G.s_ir2 = 0.0
    G.n_muestras = 0
    G.suma_spo2 = 0.0
    G.n_ventanas = 0


def iniciar_pedir_dedo():
    G.fase = FASE_PEDIR_DEDO
    G.resultado_bpm = G.resultado_spo2 = 0
    resetear_medicion()
    sensor.clear_fifo()
    print("Esperando dedo en el MAX30102...")
    actualizar_reloj_en_pantalla()


def calcular_bpm_final():
    n = len(G.bpm_lista)
    if n < 5:
        return 0
    mediana = sorted(G.bpm_lista)[n // 2]
    validos = [b for b in G.bpm_lista if mediana * 0.8 <= b <= mediana * 1.2]
    if len(validos) < 4:
        return 0
    return int(sum(validos) / len(validos) + 0.5)


def finalizar_medicion():
    G.resultado_bpm = calcular_bpm_final()
    G.resultado_spo2 = int(G.suma_spo2 / G.n_ventanas + 0.5) if G.n_ventanas >= 3 else 0
    print("Resultado -> BPM: %d   SpO2: %d" % (G.resultado_bpm, G.resultado_spo2))
    G.fase = FASE_RESULTADO
    G.inicio_resultado = ms()
    actualizar_reloj_en_pantalla()
    reportar_medicion()


def procesar_muestra(red, ir):
    if G.fase == FASE_PEDIR_DEDO:
        if ir > UMBRAL_DEDO:
            G.fase = FASE_MIDIENDO
            G.inicio_medicion = G.ultimo_dedo = ms()
            resetear_medicion()
            G.lento = G.suave = G.prev_suave = G.prev_prev_suave = float(ir)
            print("Dedo detectado. Tomando pulso...")
            actualizar_reloj_en_pantalla()
        return

    if G.fase != FASE_MIDIENDO:
        return

    if ir < UMBRAL_DEDO:
        if dt(G.ultimo_dedo) > 1500:
            print("Dedo retirado.")
            iniciar_pedir_dedo()
        return
    G.ultimo_dedo = ms()

    if dt(G.ultimo_print) >= 1000:
        G.ultimo_print = ms()
        print("IR: %d  RED: %d  latidos: %d" % (ir, red, len(G.bpm_lista)))

    transcurrido = dt(G.inicio_medicion)
    if transcurrido >= DURACION_MEDICION_MS:
        finalizar_medicion()
        return

    if transcurrido < ESPERA_ESTAB_MS:
        G.lento = G.suave = G.prev_suave = G.prev_prev_suave = float(ir)
        G.s_red = G.s_ir = G.s_red2 = G.s_ir2 = 0.0
        G.n_muestras = 0
        return

    G.lento = G.lento * 0.97 + ir * 0.03
    G.suave = G.suave * 0.7 + ir * 0.3
    pulso = G.suave - G.lento
    G.amplitud = G.amplitud * 0.995 + abs(pulso) * 0.005

    prev_pulso = G.prev_suave - G.lento
    ahora = ms()

    if (G.prev_suave > G.prev_prev_suave and G.prev_suave >= G.suave and
            prev_pulso > G.amplitud * 0.8 and prev_pulso > 15 and
            time.ticks_diff(ahora, G.ultimo_latido) > 350):
        if G.ultimo_latido > 0:
            bpm = 60000.0 / time.ticks_diff(ahora, G.ultimo_latido)
            if 45 < bpm < 170 and len(G.bpm_lista) < MAX_LATIDOS:
                G.bpm_lista.append(bpm)
        G.ultimo_latido = ahora
    G.prev_prev_suave = G.prev_suave
    G.prev_suave = G.suave

    # SpO2 (relacion AC/DC)
    G.s_red += red
    G.s_ir += ir
    G.s_red2 += red * red
    G.s_ir2 += ir * ir
    G.n_muestras += 1

    if G.n_muestras >= VENTANA_SPO2:
        n = G.n_muestras
        m_red, m_ir = G.s_red / n, G.s_ir / n
        ac_red = math.sqrt(max(0.0, G.s_red2 / n - m_red * m_red))
        ac_ir = math.sqrt(max(0.0, G.s_ir2 / n - m_ir * m_ir))
        if ac_red > 0 and ac_ir > 0:
            R = (ac_red / m_red) / (ac_ir / m_ir)
            spo2 = 110.0 - 25.0 * R
            if 80 <= spo2 <= 100:
                G.suma_spo2 += spo2
                G.n_ventanas += 1
        G.s_red = G.s_ir = G.s_red2 = G.s_ir2 = 0.0
        G.n_muestras = 0


def procesar_sensor_pulso():
    if not sensor_ok:
        return
    if G.fase not in (FASE_PEDIR_DEDO, FASE_MIDIENDO):
        return
    try:
        muestras = sensor.leer()
    except OSError:
        return
    for red, ir in muestras:
        procesar_muestra(red, ir)
        if G.fase not in (FASE_PEDIR_DEDO, FASE_MIDIENDO):
            break


def manejar_resultado():
    if G.fase != FASE_RESULTADO:
        return
    espera = TIEMPO_RESULTADO_MS if G.resultado_bpm > 0 else 3000
    if dt(G.inicio_resultado) < espera:
        return
    if G.resultado_bpm > 0:
        G.fase = FASE_CONFIRMAR
        actualizar_reloj_en_pantalla()
    else:
        iniciar_pedir_dedo()


# ==========================================================
#  MOTOR PASO A PASO (25,71 grados)
# ==========================================================
def manejar_motor():
    if not G.ejecutar_giro:
        return
    G.ejecutar_giro = False
    pasos = int(round(PASOS_POR_REVOLUCION * GRADOS_POR_GIRO / 360.0))
    print("Girando motor %.2f grados (%d pasos)..." % (GRADOS_POR_GIRO, pasos))

    sec = 0
    for _ in range(pasos):
        for pin, v in zip(motor, SECUENCIA_MOTOR[sec]):
            pin.value(v)
        sec = (sec + 1) % 8
        time.sleep_ms(3)
    for pin in motor:
        pin.value(0)

    G.pastillas_dispensadas += 1
    if G.pastillas_dispensadas >= PASTILLAS_POR_VUELTA:
        G.pastillas_dispensadas = 0
        ts = fecha_hora()
        enviar_telegram("ALERTA: el pastillero completo el giro de 360 grados (%s). Esta vacio, requiere recarga." % ts)
        enviar_sheetdb(ts, "OK", "OK", "VACIO - Recargar")


# ==========================================================
#  SERVO
# ==========================================================
def mover_servo(angulo):
    angulo = max(0, min(180, angulo))
    us = US_MIN + (US_MAX - US_MIN) * angulo // 180
    servo.duty_u16(us * 65535 // 20000)


def manejar_servo():
    if G.fase != FASE_DISPENSANDO:
        return
    if dt(G.inicio_dispensado) >= TIEMPO_ABIERTO_MS:
        mover_servo(ANGULO_CERRADO)
        G.fase = FASE_NINGUNA
        if G.estado == RELOJ_EN_VIVO:
            actualizar_reloj_en_pantalla()


# ==========================================================
#  ULTRASONICO
# ==========================================================
def medir_distancia_cm():
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    dur = time_pulse_us(echo, 1, 25000)
    if dur < 0:
        return -1
    return dur * 0.0343 / 2.0


def revisar_proximidad():
    if G.fase != FASE_ALARMA or G.estado != RELOJ_EN_VIVO:
        return
    if dt(G.ultima_medida) < 100:
        return
    G.ultima_medida = ms()

    d = medir_distancia_cm()
    cerca = DISTANCIA_MIN_CM <= d < DISTANCIA_MAX_CM
    G.lecturas_cerca = G.lecturas_cerca + 1 if cerca else 0

    if G.lecturas_cerca >= LECTURAS_NECESARIAS:
        G.lecturas_cerca = 0
        G.resultado_bpm = G.resultado_spo2 = 0
        if sensor_ok:
            iniciar_pedir_dedo()
        else:
            G.fase = FASE_CONFIRMAR
            actualizar_reloj_en_pantalla()


# ==========================================================
#  RELOJ
# ==========================================================
def avanzar_reloj():
    if not G.reloj_activo or dt(G.t_reloj) < 1000:
        return
    G.t_reloj = time.ticks_add(G.t_reloj, 1000)

    G.segundo_actual += 1
    if G.segundo_actual >= 60:
        G.segundo_actual = 0
        G.minuto_actual += 1
        if G.minuto_actual >= 60:
            G.minuto_actual = 0
            G.hora_actual += 1
            if G.hora_actual == 12:
                if G.periodo_actual == "AM":
                    G.periodo_actual = "PM"
                else:
                    G.periodo_actual = "AM"
                    G.dia_actual = (G.dia_actual + 1) % NUM_DIAS
            elif G.hora_actual > 12:
                G.hora_actual = 1

    if G.segundo_actual == 0:
        comprobar_alarma()
    if G.estado == RELOJ_EN_VIVO:
        actualizar_reloj_en_pantalla()


def comprobar_alarma():
    for h in G.horarios[G.dia_actual]:
        if h[0] == G.hora_actual and h[1] == G.minuto_actual and h[2] == (G.periodo_actual == "PM"):
            if G.fase == FASE_NINGUNA:
                G.fase = FASE_ALARMA
                G.lecturas_cerca = 0
                G.ejecutar_giro = True
            return


def manejar_buzzer():
    sonar = G.fase == FASE_ALARMA and G.estado == RELOJ_EN_VIVO and ((ms() // 300) % 2)
    buzzer.value(1 if sonar else 0)


def minutos_del_dia(hora12, minuto, es_pm):
    return ((hora12 % 12) + (12 if es_pm else 0)) * 60 + minuto


def buscar_proxima_pasta():
    ahora = G.dia_actual * 1440 + minutos_del_dia(G.hora_actual, G.minuto_actual, G.periodo_actual == "PM")
    mejor, res = -1, None
    for d in range(NUM_DIAS):
        for h in G.horarios[d]:
            delta = d * 1440 + minutos_del_dia(h[0], h[1], h[2]) - ahora
            if delta <= 0:
                delta += NUM_DIAS * 1440
            if mejor == -1 or delta < mejor:
                mejor, res = delta, (d, h)
    return mejor, res


def actualizar_reloj_en_pantalla():
    der = "[D]Ajustar" if G.fase == FASE_NINGUNA else ""
    fila0 = NOMBRES_DIAS[G.dia_actual]
    if der:
        fila0 = fila0 + " " * (20 - len(der) - len(fila0)) + der
    linea(0, fila0)
    linea(1, "HORA: %d:%s:%s %s" % (G.hora_actual, dos(G.minuto_actual),
                                    dos(G.segundo_actual), G.periodo_actual))
    f = G.fase
    if f == FASE_ALARMA:
        linea(2, "!!! HORA DE PASTA !!!")
        linea(3, "Acerca algo (<20cm)")
        return
    if f == FASE_PEDIR_DEDO:
        linea(2, "Pon el dedo en el")
        linea(3, "sensor [C]=Omitir")
        return
    if f == FASE_MIDIENDO:
        resta = max(0, DURACION_MEDICION_MS - dt(G.inicio_medicion))
        linea(2, "Tomando pulso...")
        linea(3, "Quedan %d s" % ((resta + 999) // 1000))
        return
    if f == FASE_RESULTADO:
        if G.resultado_bpm > 0:
            linea(2, "BPM: %d" % G.resultado_bpm)
            linea(3, "SpO2: " + ("%d %%" % G.resultado_spo2 if G.resultado_spo2 > 0 else "--"))
        else:
            linea(2, "Senal inestable")
            linea(3, "Intenta de nuevo")
        return
    if f == FASE_CONFIRMAR:
        if G.resultado_bpm > 0:
            linea(1, "BPM:%d SpO2:%s" % (G.resultado_bpm,
                                         "%d%%" % G.resultado_spo2 if G.resultado_spo2 > 0 else "--"))
        linea(2, "Pulsa # para soltar")
        linea(3, "las pastas")
        return
    if f == FASE_DISPENSANDO:
        resta = max(0, TIEMPO_ABIERTO_MS - dt(G.inicio_dispensado))
        linea(2, "Soltando pastas...")
        linea(3, "Cierra en %d s" % ((resta + 999) // 1000))
        return

    faltan, res = buscar_proxima_pasta()
    linea(2, "Proxima pasta:")
    if faltan == -1:
        linea(3, "Sin horarios")
    else:
        d, h = res
        linea(3, texto_horario(h[0], h[1], h[2]) + " " + NOMBRES_DIAS[d])


# ==========================================================
#  NAVEGACION Y TECLADO
# ==========================================================
_ultima_tecla = None


def leer_tecla():
    """Devuelve una tecla solo en el instante en que se pulsa."""
    global _ultima_tecla
    pulsada = None
    for r, fp in enumerate(filas):
        fp.value(1)
        for c, cp in enumerate(cols):
            if cp.value():
                pulsada = KEYS[r][c]
        fp.value(0)
        if pulsada:
            break
    if pulsada is None:
        _ultima_tecla = None
        return None
    if pulsada == _ultima_tecla:
        return None
    time.sleep_ms(20)                       # antirrebote
    _ultima_tecla = pulsada
    return pulsada


def ir(e):
    G.estado = e
    G.input_temp = ""
    if e == RELOJ_EN_VIVO:
        G.mostrando_fin_semana = False
    mostrar_pantalla()


def avanzar_configuracion():
    G.dia_config += 1
    if G.dia_config >= NUM_DIAS:
        ir(RELOJ_EN_VIVO)
    else:
        ir(PEDIR_CANTIDAD)


def tecla_a_dia(t):
    if not G.mostrando_fin_semana and t in "12345":
        return int(t) - 1
    if G.mostrando_fin_semana and t in "67":
        return int(t) - 1
    return -1


def entrada(t, max_len, mostrar):
    if t.isdigit() and len(t) == 1:
        if len(G.input_temp) < max_len:
            G.input_temp += t
            mostrar()
    elif t == "*":
        G.input_temp = ""
        mostrar()
    elif t == "#":
        return True
    return False


def leer_cantidad(t):
    if not entrada(t, 3, mostrar_entrada_cantidad) or not G.input_temp:
        return False
    G.tmp_cantidad = int(G.input_temp)
    return True


def leer_hora(t):
    if not entrada(t, 4, mostrar_entrada_hora) or len(G.input_temp) < 3:
        return False
    n = len(G.input_temp)
    G.tmp_hora = int(G.input_temp[:n - 2])
    G.tmp_min = int(G.input_temp[n - 2:])
    if G.tmp_hora < 1 or G.tmp_hora > 12 or G.tmp_min > 59:
        linea(3, "Hora invalida!")
        time.sleep_ms(1200)
        linea(3, "#=OK  *=Borrar")
        G.input_temp = ""
        mostrar_entrada_hora()
        return False
    return True


def manejar_teclado(t):
    ab = t in ("A", "B")
    e = G.estado

    if e == PEDIR_DIA:
        if t == "C":
            G.mostrando_fin_semana = not G.mostrando_fin_semana
            mostrar_pantalla_dia()
        elif tecla_a_dia(t) >= 0:
            G.dia_actual = tecla_a_dia(t)
            pantalla("", centrar("Dia " + NOMBRES_DIAS[G.dia_actual]), centrar("seleccionado"))
            time.sleep_ms(1000)
            ir(PEDIR_HORA_ACTUAL)

    elif e == PEDIR_HORA_ACTUAL:
        if leer_hora(t):
            G.hora_actual, G.minuto_actual, G.segundo_actual = G.tmp_hora, G.tmp_min, 0
            ir(PEDIR_AMPMS_ACTUAL)

    elif e == PEDIR_AMPMS_ACTUAL:
        if ab:
            G.periodo_actual = "AM" if t == "A" else "PM"
            G.segundo_actual = 0
            G.t_reloj = ms()
            G.reloj_activo = True
            G.fase = FASE_NINGUNA
            G.horarios = [[] for _ in range(NUM_DIAS)]
            G.dia_config = 0
            ir(PEDIR_CANTIDAD)

    elif e == PEDIR_CANTIDAD:
        if leer_cantidad(t):
            G.cantidad_objetivo = G.tmp_cantidad
            ir(PEDIR_CONFIRMAR_CANTIDAD)

    elif e == PEDIR_CONFIRMAR_CANTIDAD:
        if t == "A":
            G.hora_config = 0
            if G.cantidad_objetivo == 0:
                avanzar_configuracion()
            else:
                ir(PEDIR_HORA_PASTA)
        elif t == "B":
            ir(PEDIR_CANTIDAD)

    elif e == PEDIR_HORA_PASTA:
        if leer_hora(t):
            ir(PEDIR_AMPM_PASTA)

    elif e == PEDIR_AMPM_PASTA:
        if ab:
            G.horarios[G.dia_config].append([G.tmp_hora, G.tmp_min, t == "B"])
            G.hora_config += 1
            if G.hora_config >= G.cantidad_objetivo:
                avanzar_configuracion()
            else:
                ir(PEDIR_HORA_PASTA)

    elif e == RELOJ_EN_VIVO:
        if G.fase == FASE_CONFIRMAR:
            if t == "#":
                mover_servo(ANGULO_ABIERTO)
                G.inicio_dispensado = ms()
                G.fase = FASE_DISPENSANDO
                actualizar_reloj_en_pantalla()
                registrar_toma()
        elif G.fase in (FASE_PEDIR_DEDO, FASE_MIDIENDO):
            if t == "C":
                G.resultado_bpm = G.resultado_spo2 = 0
                G.fase = FASE_CONFIRMAR
                actualizar_reloj_en_pantalla()
        elif G.fase == FASE_NINGUNA:
            if t == "D":
                G.mostrando_fin_semana = False
                ir(AJUSTAR_DIA)
            elif t == "*":
                G.reloj_activo = False
                G.mostrando_fin_semana = False
                ir(PEDIR_DIA)

    elif e == AJUSTAR_DIA:
        if t == "*":
            ir(RELOJ_EN_VIVO)
        elif t == "C":
            G.mostrando_fin_semana = not G.mostrando_fin_semana
            mostrar_pantalla_dia()
        elif t == "8" and G.mostrando_fin_semana:
            ir(AJUSTAR_RELOJ_HORA)
        elif tecla_a_dia(t) >= 0:
            G.dia_ajuste = tecla_a_dia(t)
            ir(AJUSTAR_INDICE)

    elif e == AJUSTAR_INDICE:
        lst = G.horarios[G.dia_ajuste]
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_DIA)
        elif t == "A":
            ir(AJUSTAR_AGREGAR_HORA)
        elif t == "B":
            if not lst:
                linea(3, "No hay que quitar")
                time.sleep_ms(1200)
                mostrar_pantalla()
            else:
                ir(AJUSTAR_BORRAR)
        elif entrada(t, 3, mostrar_entrada_indice) and G.input_temp:
            n = int(G.input_temp)
            if 1 <= n <= len(lst):
                G.idx_ajuste = n - 1
                ir(AJUSTAR_HORA)
            else:
                linea(3, "Numero invalido!")
                time.sleep_ms(1200)
                G.input_temp = ""
                mostrar_pantalla()

    elif e == AJUSTAR_HORA:
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_INDICE)
        elif leer_hora(t):
            ir(AJUSTAR_AMPM)

    elif e == AJUSTAR_AMPM:
        if ab:
            h = G.horarios[G.dia_ajuste][G.idx_ajuste]
            h[0], h[1], h[2] = G.tmp_hora, G.tmp_min, (t == "B")
            pantalla("", "Horario cambiado!", texto_horario(h[0], h[1], h[2]))
            time.sleep_ms(1500)
            ir(RELOJ_EN_VIVO)
        elif t == "*":
            ir(AJUSTAR_HORA)

    elif e == AJUSTAR_RELOJ_HORA:
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_DIA)
        elif leer_hora(t):
            ir(AJUSTAR_RELOJ_AMPM)

    elif e == AJUSTAR_RELOJ_AMPM:
        if ab:
            pm = (t == "B")
            pantalla("", "Hora cambiada!", texto_horario(G.tmp_hora, G.tmp_min, pm))
            time.sleep_ms(1500)
            G.hora_actual, G.minuto_actual, G.segundo_actual = G.tmp_hora, G.tmp_min, 0
            G.periodo_actual = "PM" if pm else "AM"
            G.t_reloj = ms()
            ir(RELOJ_EN_VIVO)
        elif t == "*":
            ir(AJUSTAR_RELOJ_HORA)

    elif e == AJUSTAR_AGREGAR_HORA:
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_INDICE)
        elif leer_hora(t):
            ir(AJUSTAR_AGREGAR_AMPM)

    elif e == AJUSTAR_AGREGAR_AMPM:
        if ab:
            G.horarios[G.dia_ajuste].append([G.tmp_hora, G.tmp_min, t == "B"])
            pantalla("", "Horario agregado!", texto_horario(G.tmp_hora, G.tmp_min, t == "B"))
            time.sleep_ms(1500)
            ir(AJUSTAR_INDICE)
        elif t == "*":
            ir(AJUSTAR_AGREGAR_HORA)

    elif e == AJUSTAR_BORRAR:
        lst = G.horarios[G.dia_ajuste]
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_INDICE)
        elif entrada(t, 3, mostrar_entrada_indice) and G.input_temp:
            n = int(G.input_temp)
            if 1 <= n <= len(lst):
                h = lst.pop(n - 1)
                pantalla("", "Horario borrado!", texto_horario(h[0], h[1], h[2]))
                time.sleep_ms(1500)
                ir(AJUSTAR_INDICE)
            else:
                linea(3, "Numero invalido!")
                time.sleep_ms(1200)
                G.input_temp = ""
                mostrar_pantalla()


# ==========================================================
#  PROGRAMA PRINCIPAL
# ==========================================================
def main():
    global sensor, sensor_ok
    mover_servo(ANGULO_CERRADO)

    try:
        sensor = MAX30102(i2c)
        sensor_ok = True
        print("MAX30102 listo.")
    except Exception as ex:
        print("MAX30102 NO detectado. Se omitira la medicion.", ex)
        pantalla("", "Sensor de pulso", "NO detectado")
        time.sleep_ms(2000)# ==========================================================
#  PASTILLERO - MicroPython (ESP32)
#  Pines iguales al codigo de Arduino
# ==========================================================
import time, math, json
import network, ntptime
from machine import Pin, I2C, PWM, time_pulse_us

try:
    import urequests as requests
except ImportError:
    import requests

# ---------------- RED Y SERVICIOS ----------------
WIFI_SSID = "yomellamopablo"
WIFI_PASS = "salchipapa123456789"
TELEGRAM_TOKEN = "9134172375:AAGFleW3JhOytfMqQGnpJC3zfAr1BjTwEPM"
TELEGRAM_CHAT_ID = "7912478824"
SHEETDB_URL = "https://sheetdb.io/api/v1/fyz0e3drzv0bv"
AIO_USER = "teawen"
AIO_KEY = "aio_axXu00FXSfDVST3WOATxNCtCoHxA"

GMT_OFFSET_SEC = -18000                 # Colombia (UTC-5)
TIEMPO_SIN_PRESENCIA_MS = 300000        # 5 min
TIEMPO_SIN_CONFIRMAR_MS = 120000        # 2 min

# ---------------- GIRO DEL PASTILLERO ----------------
GRADOS_POR_GIRO = 25.71
PASTILLAS_POR_VUELTA = 14
PASOS_POR_REVOLUCION = 4096

# ---------------- PINES ----------------
PIN_BUZZER = 15
PIN_TRIG, PIN_ECHO = 5, 23
IN_PINS = (16, 17, 18, 19)
PIN_SERVO = 4
SDA, SCL = 21, 22
FILAS_PINS = (13, 12, 14, 27)
COLS_PINS = (26, 25, 33, 32)

# ---------------- PARAMETROS ----------------
DISTANCIA_MIN_CM, DISTANCIA_MAX_CM = 2.0, 20.0
LECTURAS_NECESARIAS = 5
ANGULO_CERRADO, ANGULO_ABIERTO = 0, 90
TIEMPO_ABIERTO_MS = 5000
US_MIN, US_MAX = 500, 2500

UMBRAL_DEDO = 20000
DURACION_MEDICION_MS = 15000
ESPERA_ESTAB_MS = 3000
TIEMPO_RESULTADO_MS = 6000
VENTANA_SPO2 = 50
MAX_LATIDOS = 100

NUM_DIAS = 7
NOMBRES_DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]

KEYS = (("1", "2", "3", "A"),
        ("4", "5", "6", "B"),
        ("7", "8", "9", "C"),
        ("*", "0", "#", "D"))

# ---------------- ESTADOS Y FASES ----------------
(PEDIR_DIA, PEDIR_HORA_ACTUAL, PEDIR_AMPMS_ACTUAL, PEDIR_CANTIDAD,
 PEDIR_CONFIRMAR_CANTIDAD, PEDIR_HORA_PASTA, PEDIR_AMPM_PASTA, RELOJ_EN_VIVO,
 AJUSTAR_DIA, AJUSTAR_INDICE, AJUSTAR_HORA, AJUSTAR_AMPM, AJUSTAR_RELOJ_HORA,
 AJUSTAR_RELOJ_AMPM, AJUSTAR_AGREGAR_HORA, AJUSTAR_AGREGAR_AMPM,
 AJUSTAR_BORRAR) = range(17)

(FASE_NINGUNA, FASE_ALARMA, FASE_PEDIR_DEDO, FASE_MIDIENDO, FASE_RESULTADO,
 FASE_CONFIRMAR, FASE_DISPENSANDO) = range(7)


# ==========================================================
#  DRIVER LCD I2C (PCF8574) 20x4
# ==========================================================
class LCD:
    def __init__(self, i2c, addr=0x27, cols=20, rows=4):
        self.i2c, self.addr = i2c, addr
        self.bl = 0x08
        self.offs = (0x00, 0x40, 0x14, 0x54)
        time.sleep_ms(50)
        for _ in range(3):
            self._send4(0x30, 0)
            time.sleep_ms(5)
        self._send4(0x20, 0)
        self._cmd(0x28)
        self._cmd(0x0C)
        self._cmd(0x06)
        self.clear()

    def _w(self, b):
        self.i2c.writeto(self.addr, bytes([b | self.bl]))

    def _send4(self, n, rs):
        b = (n & 0xF0) | rs
        self._w(b | 0x04)
        time.sleep_us(2)
        self._w(b & ~0x04)
        time.sleep_us(60)

    def _cmd(self, c):
        self._send4(c, 0)
        self._send4(c << 4, 0)

    def _char(self, c):
        self._send4(c, 1)
        self._send4(c << 4, 1)

    def clear(self):
        self._cmd(0x01)
        time.sleep_ms(3)

    def puts(self, col, row, s):
        self._cmd(0x80 | (col + self.offs[row]))
        for ch in s:
            self._char(ord(ch) & 0xFF)


# ==========================================================
#  DRIVER MAX30102 (minimo)
# ==========================================================
class MAX30102:
    ADDR = 0x57

    def __init__(self, i2c):
        self.i2c = i2c
        if self.i2c.readfrom_mem(self.ADDR, 0xFF, 1)[0] != 0x15:
            raise OSError("MAX30102 no responde")
        self.i2c.writeto_mem(self.ADDR, 0x09, b"\x40")      # reset
        time.sleep_ms(100)
        self.i2c.writeto_mem(self.ADDR, 0x08, b"\x50")      # avg 4, rollover
        self.i2c.writeto_mem(self.ADDR, 0x09, b"\x03")      # modo SpO2 (rojo+IR)
        # rango 4096, 400 muestras/s, pulso 411us  (400/4 = 100 muestras/s)
        self.i2c.writeto_mem(self.ADDR, 0x0A, b"\x2F")
        self.i2c.writeto_mem(self.ADDR, 0x0C, bytes([20]))  # LED rojo
        self.i2c.writeto_mem(self.ADDR, 0x0D, bytes([20]))  # LED IR
        self.clear_fifo()

    def clear_fifo(self):
        for r in (0x04, 0x05, 0x06):
            self.i2c.writeto_mem(self.ADDR, r, b"\x00")

    def leer(self):
        """Devuelve lista de (rojo, ir) con las muestras nuevas."""
        wr = self.i2c.readfrom_mem(self.ADDR, 0x04, 1)[0]
        rd = self.i2c.readfrom_mem(self.ADDR, 0x06, 1)[0]
        n = (wr - rd) & 0x1F
        if n == 0:
            return []
        d = self.i2c.readfrom_mem(self.ADDR, 0x07, n * 6)
        out = []
        for i in range(n):
            o = i * 6
            red = ((d[o] << 16) | (d[o + 1] << 8) | d[o + 2]) & 0x3FFFF
            ir = ((d[o + 3] << 16) | (d[o + 4] << 8) | d[o + 5]) & 0x3FFFF
            out.append((red, ir))
        return out


# ==========================================================
#  HARDWARE
# ==========================================================
i2c = I2C(0, sda=Pin(SDA), scl=Pin(SCL), freq=100000)
lcd = LCD(i2c)

buzzer = Pin(PIN_BUZZER, Pin.OUT)
trig = Pin(PIN_TRIG, Pin.OUT)
echo = Pin(PIN_ECHO, Pin.IN, Pin.PULL_DOWN)
trig.value(0)
motor = [Pin(p, Pin.OUT) for p in IN_PINS]
servo = PWM(Pin(PIN_SERVO), freq=50)
filas = [Pin(p, Pin.OUT, value=0) for p in FILAS_PINS]
cols = [Pin(p, Pin.IN, Pin.PULL_DOWN) for p in COLS_PINS]

SECUENCIA_MOTOR = ((1, 0, 0, 0), (1, 1, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0),
                   (0, 0, 1, 0), (0, 0, 1, 1), (0, 0, 0, 1), (1, 0, 0, 1))

sensor = None
sensor_ok = False
wlan = network.WLAN(network.STA_IF)


# ==========================================================
#  ESTADO GLOBAL
# ==========================================================
class G:
    estado = PEDIR_DIA
    fase = FASE_NINGUNA
    ejecutar_giro = False
    pastillas_dispensadas = 0

    dia_actual, hora_actual, minuto_actual, segundo_actual = 0, 5, 17, 0
    periodo_actual = "PM"
    reloj_activo = False
    mostrando_fin_semana = False
    t_reloj = 0

    horarios = [[] for _ in range(NUM_DIAS)]    # cada uno: [hora, minuto, es_pm]
    dia_config = hora_config = cantidad_objetivo = 0
    tmp_hora = tmp_min = tmp_cantidad = 0
    dia_ajuste = idx_ajuste = 0
    input_temp = ""

    inicio_dispensado = ultima_medida = lecturas_cerca = 0
    inicio_fase_alerta = 0
    alerta_enviada = False
    fase_ant = FASE_NINGUNA

    inicio_medicion = ultimo_dedo = inicio_resultado = 0
    ultimo_print = 0
    lento = suave = prev_suave = prev_prev_suave = amplitud = 0.0
    ultimo_latido = 0
    bpm_lista = []
    s_red = s_ir = s_red2 = s_ir2 = 0.0
    n_muestras = 0
    suma_spo2 = 0.0
    n_ventanas = 0
    resultado_bpm = resultado_spo2 = 0

    ntp_ok = False
    wifi_estaba = True


def ms():
    return time.ticks_ms()


def dt(desde):
    return time.ticks_diff(time.ticks_ms(), desde)


# ==========================================================
#  UTILIDADES DE TEXTO Y PANTALLA
# ==========================================================
def dos(n):
    return "0%d" % n if n < 10 else str(n)


def pad(s):
    return (s + " " * 20)[:20]


def centrar(s):
    return pad(" " * ((20 - len(s)) // 2) + s)


def texto_horario(h, m, pm):
    return "%d:%s %s" % (h, dos(m), "PM" if pm else "AM")


def linea(fila, s):
    lcd.puts(0, fila, pad(s))


def pantalla(a="", b="", c="", d=""):
    lcd.clear()
    for i, s in enumerate((a, b, c, d)):
        if s:
            lcd.puts(0, i, s[:20])


def pantalla_hora(a, b):
    pantalla(a, b, "Hora: _:__", "#=OK  *=Borrar")


def cab_config():
    return "%s %d/%d" % (NOMBRES_DIAS[G.dia_config], G.hora_config + 1, G.cantidad_objetivo)


def cab_ajuste():
    return "%s #%d" % (NOMBRES_DIAS[G.dia_ajuste], G.idx_ajuste + 1)


def mostrar_entrada_cantidad():
    lcd.puts(10, 2, (G.input_temp or "_") + "      ")


def mostrar_entrada_hora():
    n = len(G.input_temp)
    h = "_" if n == 0 else (G.input_temp if n < 3 else G.input_temp[:n - 2])
    m = ("_" if n == 2 else "__") if n < 3 else G.input_temp[n - 2:]
    lcd.puts(6, 2, h + ":" + m + "      ")


def mostrar_entrada_indice():
    s = "Num: " + (G.input_temp or "_")
    n = int(G.input_temp) if G.input_temp else 0
    lst = G.horarios[G.dia_ajuste]
    if 1 <= n <= len(lst):
        h = lst[n - 1]
        s += " " + texto_horario(h[0], h[1], h[2])
    linea(2, s)


def mostrar_pantalla_dia():
    aj = (G.estado == AJUSTAR_DIA)
    titulo = "Ajustar cual dia?" if aj else "Que dia es hoy?"
    if not G.mostrando_fin_semana:
        pantalla(titulo, "1.Lunes  2.Martes", "3.Mier 4.Jue 5.Vie",
                 "1-5 C=Sab/Dom *=Sal" if aj else "Pulsa 1-5, C=Sab/Dom")
    else:
        pantalla(titulo, "6.Sabado 7.Domingo", "8.Cambiar hora" if aj else "",
                 "6-7 C=volver *=Salir" if aj else "Pulsa 6-7, C=volver")


def mostrar_pantalla():
    e = G.estado
    nueva = "Hora nueva: %d:%s" % (G.tmp_hora, dos(G.tmp_min))
    if e in (PEDIR_DIA, AJUSTAR_DIA):
        mostrar_pantalla_dia()
    elif e == PEDIR_HORA_ACTUAL:
        pantalla_hora("Hora del " + NOMBRES_DIAS[G.dia_actual], "Escribe la hora:")
    elif e == PEDIR_AMPMS_ACTUAL:
        pantalla("Es AM o PM?", "[A] -> AM", "[B] -> PM")
    elif e == PEDIR_CANTIDAD:
        pantalla("Dia: " + NOMBRES_DIAS[G.dia_config], "Cuantos horarios?",
                 "Cantidad: _", "#=OK  *=Borrar")
    elif e == PEDIR_CONFIRMAR_CANTIDAD:
        pantalla("Dia: " + NOMBRES_DIAS[G.dia_config],
                 "Sin horarios?" if G.cantidad_objetivo == 0
                 else "Son %d horarios?" % G.cantidad_objetivo,
                 "Estas seguro?", "[A]=Si  [B]=No")
    elif e == PEDIR_HORA_PASTA:
        pantalla_hora(cab_config(), "Hora de la pasta:")
    elif e == PEDIR_AMPM_PASTA:
        pantalla(cab_config(), "Es AM o PM?", "[A] -> AM", "[B] -> PM")
    elif e == RELOJ_EN_VIVO:
        lcd.clear()
        actualizar_reloj_en_pantalla()
    elif e == AJUSTAR_INDICE:
        pantalla("Ajustar " + NOMBRES_DIAS[G.dia_ajuste],
                 "Hay %d horarios #=OK" % len(G.horarios[G.dia_ajuste]),
                 "", "A=Agregar B=Quitar")
        mostrar_entrada_indice()
    elif e == AJUSTAR_HORA:
        h = G.horarios[G.dia_ajuste][G.idx_ajuste]
        pantalla_hora(cab_ajuste(), "Actual: " + texto_horario(h[0], h[1], h[2]))
    elif e == AJUSTAR_AMPM:
        pantalla(cab_ajuste(), nueva, "[A]=AM  [B]=PM", "*=Atras")
    elif e == AJUSTAR_RELOJ_HORA:
        pantalla_hora("Cambiar hora actual", "Hoy es " + NOMBRES_DIAS[G.dia_actual])
    elif e == AJUSTAR_RELOJ_AMPM:
        pantalla("Cambiar hora actual", nueva, "[A]=AM  [B]=PM", "*=Atras")
    elif e == AJUSTAR_AGREGAR_HORA:
        pantalla_hora("Agregar " + NOMBRES_DIAS[G.dia_ajuste], "Hora de la pasta:")
    elif e == AJUSTAR_AGREGAR_AMPM:
        pantalla("Agregar " + NOMBRES_DIAS[G.dia_ajuste],
                 "Hora: %d:%s" % (G.tmp_hora, dos(G.tmp_min)), "[A]=AM  [B]=PM", "*=Atras")
    elif e == AJUSTAR_BORRAR:
        pantalla("Quitar en " + NOMBRES_DIAS[G.dia_ajuste], "Cual horario borrar?",
                 "", "#=OK *=Borrar/Atras")
        mostrar_entrada_indice()


# ==========================================================
#  WIFI, TELEGRAM, SHEETDB, ADAFRUIT
# ==========================================================
def http_post(url, datos, headers=None):
    headers = headers or {}
    headers["Content-Type"] = "application/json"
    try:
        try:
            r = requests.post(url, data=json.dumps(datos), headers=headers, timeout=6)
        except TypeError:                       # versiones sin parametro timeout
            r = requests.post(url, data=json.dumps(datos), headers=headers)
        codigo = r.status_code
        r.close()
        return codigo
    except Exception as ex:
        print("HTTP error:", ex)
        return -1


def hay_wifi():
    ok = wlan.isconnected()
    if ok and not G.wifi_estaba:
        print("WiFi reconectado.")
    if not ok and G.wifi_estaba:
        print("WiFi perdido. Reintentando...")
        try:
            wlan.connect(WIFI_SSID, WIFI_PASS)
        except Exception:
            pass
    G.wifi_estaba = ok
    return ok


def fecha_hora():
    if G.ntp_ok:
        t = time.localtime(time.time() + GMT_OFFSET_SEC)
        return "%04d-%02d-%02d %02d:%02d:%02d" % t[:6]
    return "%s %d:%s %s" % (NOMBRES_DIAS[G.dia_actual], G.hora_actual,
                            dos(G.minuto_actual), G.periodo_actual)


def enviar_telegram(mensaje):
    if not hay_wifi():
        return
    url = "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_TOKEN
    c = http_post(url, {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje})
    print("Telegram HTTP Code:", c)


def enviar_sheetdb(hora, ultra, tecla, pt_lleno, bpm="--", spo2="--"):
    if not hay_wifi():
        print("SheetDB: sin WiFi")
        return
    fila = {"DIA": NOMBRES_DIAS[G.dia_actual], "HORA PST": hora,
            "ALERTA ULT": ultra, "ALERTA TCD": tecla, "ALERTA PST VACIO": pt_lleno}
    # Si tu hoja tiene columnas BPM y SPO2, descomenta estas dos lineas:
    # fila["BPM"] = bpm; fila["SPO2"] = spo2
    c = http_post(SHEETDB_URL, {"data": [fila]})
    print("SheetDB HTTP Code:", c)


def enviar_adafruit(feed, valor):
    if not hay_wifi():
        return
    url = "https://io.adafruit.com/api/v2/%s/feeds/%s/data" % (AIO_USER, feed)
    c = http_post(url, {"value": valor}, {"X-AIO-Key": AIO_KEY})
    print("Adafruit HTTP Code (%s): %s" % (feed, c))


def reportar_medicion():
    ts = fecha_hora()
    if G.resultado_bpm > 0:
        enviar_adafruit("bpm", G.resultado_bpm)
        if G.resultado_bpm < 60 or G.resultado_bpm > 100:
            enviar_telegram("ALERTA: pulsaciones fuera de rango: %d BPM (%s)." % (G.resultado_bpm, ts))
    if G.resultado_spo2 > 0:
        enviar_adafruit("oxigenacion", G.resultado_spo2)
        if G.resultado_spo2 < 90:
            enviar_telegram("ALERTA: oxigenacion baja: %d%% (%s)." % (G.resultado_spo2, ts))


def registrar_toma():
    ts = fecha_hora()
    enviar_sheetdb(ts, "OK", "OK", "OK",
                   str(G.resultado_bpm) if G.resultado_bpm > 0 else "--",
                   str(G.resultado_spo2) if G.resultado_spo2 > 0 else "--")
    enviar_telegram("Pasta tomada a las %s." % ts)


def revisar_alertas():
    if G.fase != G.fase_ant:
        G.fase_ant = G.fase
        G.inicio_fase_alerta = ms()
        G.alerta_enviada = False
    if G.alerta_enviada:
        return
    if G.fase == FASE_ALARMA and dt(G.inicio_fase_alerta) >= TIEMPO_SIN_PRESENCIA_MS:
        G.alerta_enviada = True
        ts = fecha_hora()
        enviar_telegram("ALERTA: pasaron mas de 5 minutos sin movimiento frente al pastillero (%s)." % ts)
        enviar_sheetdb(ts, "Alerta: sin movimiento > 5 min", "OK", "OK")
    if G.fase == FASE_CONFIRMAR and dt(G.inicio_fase_alerta) >= TIEMPO_SIN_CONFIRMAR_MS:
        G.alerta_enviada = True
        ts = fecha_hora()
        enviar_telegram("ADVERTENCIA: presencia detectada pero no se confirmo con # (%s)." % ts)
        enviar_sheetdb(ts, "OK", "Alerta: sin confirmacion en teclado", "OK")


def conectar_wifi():
    pantalla("", centrar("Conectando WiFi"))
    print("Conectando a WiFi...")
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    t0 = ms()
    puntos = 0
    while not wlan.isconnected() and dt(t0) < 10000:
        time.sleep_ms(500)
        puntos = (puntos + 1) % 4
        linea(2, centrar("." * puntos))

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print("WiFi conectado exitosamente. IP:", ip)
        pantalla("", centrar("WiFi conectado!"), centrar(ip))
        time.sleep_ms(2000)
        try:
            ntptime.settime()
            G.ntp_ok = True
        except Exception as ex:
            print("NTP fallo:", ex)

        print("=== PRUEBA DE SERVICIOS ===")
        enviar_telegram("Pastillero conectado exitosamente.")
        enviar_sheetdb("PRUEBA INICIO", "OK", "OK", "OK")
        print("=== FIN PRUEBA ===")
    else:
        print("Sin WiFi: el pastillero funciona, pero no enviara datos.")
        pantalla("", centrar("Sin WiFi"), centrar("Modo sin conexion"))
        time.sleep_ms(2500)


# ==========================================================
#  MEDICION DE PULSO Y SpO2
# ==========================================================
def resetear_medicion():
    G.bpm_lista = []
    G.ultimo_latido = 0
    G.amplitud = 0.0
    G.s_red = G.s_ir = G.s_red2 = G.s_ir2 = 0.0
    G.n_muestras = 0
    G.suma_spo2 = 0.0
    G.n_ventanas = 0


def iniciar_pedir_dedo():
    G.fase = FASE_PEDIR_DEDO
    G.resultado_bpm = G.resultado_spo2 = 0
    resetear_medicion()
    sensor.clear_fifo()
    print("Esperando dedo en el MAX30102...")
    actualizar_reloj_en_pantalla()


def calcular_bpm_final():
    n = len(G.bpm_lista)
    if n < 5:
        return 0
    mediana = sorted(G.bpm_lista)[n // 2]
    validos = [b for b in G.bpm_lista if mediana * 0.8 <= b <= mediana * 1.2]
    if len(validos) < 4:
        return 0
    return int(sum(validos) / len(validos) + 0.5)


def finalizar_medicion():
    G.resultado_bpm = calcular_bpm_final()
    G.resultado_spo2 = int(G.suma_spo2 / G.n_ventanas + 0.5) if G.n_ventanas >= 3 else 0
    print("Resultado -> BPM: %d   SpO2: %d" % (G.resultado_bpm, G.resultado_spo2))
    G.fase = FASE_RESULTADO
    G.inicio_resultado = ms()
    actualizar_reloj_en_pantalla()
    reportar_medicion()


def procesar_muestra(red, ir):
    if G.fase == FASE_PEDIR_DEDO:
        if ir > UMBRAL_DEDO:
            G.fase = FASE_MIDIENDO
            G.inicio_medicion = G.ultimo_dedo = ms()
            resetear_medicion()
            G.lento = G.suave = G.prev_suave = G.prev_prev_suave = float(ir)
            print("Dedo detectado. Tomando pulso...")
            actualizar_reloj_en_pantalla()
        return

    if G.fase != FASE_MIDIENDO:
        return

    if ir < UMBRAL_DEDO:
        if dt(G.ultimo_dedo) > 1500:
            print("Dedo retirado.")
            iniciar_pedir_dedo()
        return
    G.ultimo_dedo = ms()

    if dt(G.ultimo_print) >= 1000:
        G.ultimo_print = ms()
        print("IR: %d  RED: %d  latidos: %d" % (ir, red, len(G.bpm_lista)))

    transcurrido = dt(G.inicio_medicion)
    if transcurrido >= DURACION_MEDICION_MS:
        finalizar_medicion()
        return

    if transcurrido < ESPERA_ESTAB_MS:
        G.lento = G.suave = G.prev_suave = G.prev_prev_suave = float(ir)
        G.s_red = G.s_ir = G.s_red2 = G.s_ir2 = 0.0
        G.n_muestras = 0
        return

    G.lento = G.lento * 0.97 + ir * 0.03
    G.suave = G.suave * 0.7 + ir * 0.3
    pulso = G.suave - G.lento
    G.amplitud = G.amplitud * 0.995 + abs(pulso) * 0.005

    prev_pulso = G.prev_suave - G.lento
    ahora = ms()

    if (G.prev_suave > G.prev_prev_suave and G.prev_suave >= G.suave and
            prev_pulso > G.amplitud * 0.8 and prev_pulso > 15 and
            time.ticks_diff(ahora, G.ultimo_latido) > 350):
        if G.ultimo_latido > 0:
            bpm = 60000.0 / time.ticks_diff(ahora, G.ultimo_latido)
            if 45 < bpm < 170 and len(G.bpm_lista) < MAX_LATIDOS:
                G.bpm_lista.append(bpm)
        G.ultimo_latido = ahora
    G.prev_prev_suave = G.prev_suave
    G.prev_suave = G.suave

    # SpO2 (relacion AC/DC)
    G.s_red += red
    G.s_ir += ir
    G.s_red2 += red * red
    G.s_ir2 += ir * ir
    G.n_muestras += 1

    if G.n_muestras >= VENTANA_SPO2:
        n = G.n_muestras
        m_red, m_ir = G.s_red / n, G.s_ir / n
        ac_red = math.sqrt(max(0.0, G.s_red2 / n - m_red * m_red))
        ac_ir = math.sqrt(max(0.0, G.s_ir2 / n - m_ir * m_ir))
        if ac_red > 0 and ac_ir > 0:
            R = (ac_red / m_red) / (ac_ir / m_ir)
            spo2 = 110.0 - 25.0 * R
            if 80 <= spo2 <= 100:
                G.suma_spo2 += spo2
                G.n_ventanas += 1
        G.s_red = G.s_ir = G.s_red2 = G.s_ir2 = 0.0
        G.n_muestras = 0


def procesar_sensor_pulso():
    if not sensor_ok:
        return
    if G.fase not in (FASE_PEDIR_DEDO, FASE_MIDIENDO):
        return
    try:
        muestras = sensor.leer()
    except OSError:
        return
    for red, ir in muestras:
        procesar_muestra(red, ir)
        if G.fase not in (FASE_PEDIR_DEDO, FASE_MIDIENDO):
            break


def manejar_resultado():
    if G.fase != FASE_RESULTADO:
        return
    espera = TIEMPO_RESULTADO_MS if G.resultado_bpm > 0 else 3000
    if dt(G.inicio_resultado) < espera:
        return
    if G.resultado_bpm > 0:
        G.fase = FASE_CONFIRMAR
        actualizar_reloj_en_pantalla()
    else:
        iniciar_pedir_dedo()


# ==========================================================
#  MOTOR PASO A PASO (25,71 grados)
# ==========================================================
def manejar_motor():
    if not G.ejecutar_giro:
        return
    G.ejecutar_giro = False
    pasos = int(round(PASOS_POR_REVOLUCION * GRADOS_POR_GIRO / 360.0))
    print("Girando motor %.2f grados (%d pasos)..." % (GRADOS_POR_GIRO, pasos))

    sec = 0
    for _ in range(pasos):
        for pin, v in zip(motor, SECUENCIA_MOTOR[sec]):
            pin.value(v)
        sec = (sec + 1) % 8
        time.sleep_ms(3)
    for pin in motor:
        pin.value(0)

    G.pastillas_dispensadas += 1
    if G.pastillas_dispensadas >= PASTILLAS_POR_VUELTA:
        G.pastillas_dispensadas = 0
        ts = fecha_hora()
        enviar_telegram("ALERTA: el pastillero completo el giro de 360 grados (%s). Esta vacio, requiere recarga." % ts)
        enviar_sheetdb(ts, "OK", "OK", "VACIO - Recargar")


# ==========================================================
#  SERVO
# ==========================================================
def mover_servo(angulo):
    angulo = max(0, min(180, angulo))
    us = US_MIN + (US_MAX - US_MIN) * angulo // 180
    servo.duty_u16(us * 65535 // 20000)


def manejar_servo():
    if G.fase != FASE_DISPENSANDO:
        return
    if dt(G.inicio_dispensado) >= TIEMPO_ABIERTO_MS:
        mover_servo(ANGULO_CERRADO)
        G.fase = FASE_NINGUNA
        if G.estado == RELOJ_EN_VIVO:
            actualizar_reloj_en_pantalla()


# ==========================================================
#  ULTRASONICO
# ==========================================================
def medir_distancia_cm():
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    dur = time_pulse_us(echo, 1, 25000)
    if dur < 0:
        return -1
    return dur * 0.0343 / 2.0


def revisar_proximidad():
    if G.fase != FASE_ALARMA or G.estado != RELOJ_EN_VIVO:
        return
    if dt(G.ultima_medida) < 100:
        return
    G.ultima_medida = ms()

    d = medir_distancia_cm()
    cerca = DISTANCIA_MIN_CM <= d < DISTANCIA_MAX_CM
    G.lecturas_cerca = G.lecturas_cerca + 1 if cerca else 0

    if G.lecturas_cerca >= LECTURAS_NECESARIAS:
        G.lecturas_cerca = 0
        G.resultado_bpm = G.resultado_spo2 = 0
        if sensor_ok:
            iniciar_pedir_dedo()
        else:
            G.fase = FASE_CONFIRMAR
            actualizar_reloj_en_pantalla()


# ==========================================================
#  RELOJ
# ==========================================================
def avanzar_reloj():
    if not G.reloj_activo or dt(G.t_reloj) < 1000:
        return
    G.t_reloj = time.ticks_add(G.t_reloj, 1000)

    G.segundo_actual += 1
    if G.segundo_actual >= 60:
        G.segundo_actual = 0
        G.minuto_actual += 1
        if G.minuto_actual >= 60:
            G.minuto_actual = 0
            G.hora_actual += 1
            if G.hora_actual == 12:
                if G.periodo_actual == "AM":
                    G.periodo_actual = "PM"
                else:
                    G.periodo_actual = "AM"
                    G.dia_actual = (G.dia_actual + 1) % NUM_DIAS
            elif G.hora_actual > 12:
                G.hora_actual = 1

    if G.segundo_actual == 0:
        comprobar_alarma()
    if G.estado == RELOJ_EN_VIVO:
        actualizar_reloj_en_pantalla()


def comprobar_alarma():
    for h in G.horarios[G.dia_actual]:
        if h[0] == G.hora_actual and h[1] == G.minuto_actual and h[2] == (G.periodo_actual == "PM"):
            if G.fase == FASE_NINGUNA:
                G.fase = FASE_ALARMA
                G.lecturas_cerca = 0
                G.ejecutar_giro = True
            return


def manejar_buzzer():
    sonar = G.fase == FASE_ALARMA and G.estado == RELOJ_EN_VIVO and ((ms() // 300) % 2)
    buzzer.value(1 if sonar else 0)


def minutos_del_dia(hora12, minuto, es_pm):
    return ((hora12 % 12) + (12 if es_pm else 0)) * 60 + minuto


def buscar_proxima_pasta():
    ahora = G.dia_actual * 1440 + minutos_del_dia(G.hora_actual, G.minuto_actual, G.periodo_actual == "PM")
    mejor, res = -1, None
    for d in range(NUM_DIAS):
        for h in G.horarios[d]:
            delta = d * 1440 + minutos_del_dia(h[0], h[1], h[2]) - ahora
            if delta <= 0:
                delta += NUM_DIAS * 1440
            if mejor == -1 or delta < mejor:
                mejor, res = delta, (d, h)
    return mejor, res


def actualizar_reloj_en_pantalla():
    der = "[D]Ajustar" if G.fase == FASE_NINGUNA else ""
    fila0 = NOMBRES_DIAS[G.dia_actual]
    if der:
        fila0 = fila0 + " " * (20 - len(der) - len(fila0)) + der
    linea(0, fila0)
    linea(1, "HORA: %d:%s:%s %s" % (G.hora_actual, dos(G.minuto_actual),
                                    dos(G.segundo_actual), G.periodo_actual))
    f = G.fase
    if f == FASE_ALARMA:
        linea(2, "!!! HORA DE PASTA !!!")
        linea(3, "Acerca algo (<20cm)")
        return
    if f == FASE_PEDIR_DEDO:
        linea(2, "Pon el dedo en el")
        linea(3, "sensor [C]=Omitir")
        return
    if f == FASE_MIDIENDO:
        resta = max(0, DURACION_MEDICION_MS - dt(G.inicio_medicion))
        linea(2, "Tomando pulso...")
        linea(3, "Quedan %d s" % ((resta + 999) // 1000))
        return
    if f == FASE_RESULTADO:
        if G.resultado_bpm > 0:
            linea(2, "BPM: %d" % G.resultado_bpm)
            linea(3, "SpO2: " + ("%d %%" % G.resultado_spo2 if G.resultado_spo2 > 0 else "--"))
        else:
            linea(2, "Senal inestable")
            linea(3, "Intenta de nuevo")
        return
    if f == FASE_CONFIRMAR:
        if G.resultado_bpm > 0:
            linea(1, "BPM:%d SpO2:%s" % (G.resultado_bpm,
                                         "%d%%" % G.resultado_spo2 if G.resultado_spo2 > 0 else "--"))
        linea(2, "Pulsa # para soltar")
        linea(3, "las pastas")
        return
    if f == FASE_DISPENSANDO:
        resta = max(0, TIEMPO_ABIERTO_MS - dt(G.inicio_dispensado))
        linea(2, "Soltando pastas...")
        linea(3, "Cierra en %d s" % ((resta + 999) // 1000))
        return

    faltan, res = buscar_proxima_pasta()
    linea(2, "Proxima pasta:")
    if faltan == -1:
        linea(3, "Sin horarios")
    else:
        d, h = res
        linea(3, texto_horario(h[0], h[1], h[2]) + " " + NOMBRES_DIAS[d])


# ==========================================================
#  NAVEGACION Y TECLADO
# ==========================================================
_ultima_tecla = None


def leer_tecla():
    """Devuelve una tecla solo en el instante en que se pulsa."""
    global _ultima_tecla
    pulsada = None
    for r, fp in enumerate(filas):
        fp.value(1)
        for c, cp in enumerate(cols):
            if cp.value():
                pulsada = KEYS[r][c]
        fp.value(0)
        if pulsada:
            break
    if pulsada is None:
        _ultima_tecla = None
        return None
    if pulsada == _ultima_tecla:
        return None
    time.sleep_ms(20)                       # antirrebote
    _ultima_tecla = pulsada
    return pulsada


def ir(e):
    G.estado = e
    G.input_temp = ""
    if e == RELOJ_EN_VIVO:
        G.mostrando_fin_semana = False
    mostrar_pantalla()


def avanzar_configuracion():
    G.dia_config += 1
    if G.dia_config >= NUM_DIAS:
        ir(RELOJ_EN_VIVO)
    else:
        ir(PEDIR_CANTIDAD)


def tecla_a_dia(t):
    if not G.mostrando_fin_semana and t in "12345":
        return int(t) - 1
    if G.mostrando_fin_semana and t in "67":
        return int(t) - 1
    return -1


def entrada(t, max_len, mostrar):
    if t.isdigit() and len(t) == 1:
        if len(G.input_temp) < max_len:
            G.input_temp += t
            mostrar()
    elif t == "*":
        G.input_temp = ""
        mostrar()
    elif t == "#":
        return True
    return False


def leer_cantidad(t):
    if not entrada(t, 3, mostrar_entrada_cantidad) or not G.input_temp:
        return False
    G.tmp_cantidad = int(G.input_temp)
    return True


def leer_hora(t):
    if not entrada(t, 4, mostrar_entrada_hora) or len(G.input_temp) < 3:
        return False
    n = len(G.input_temp)
    G.tmp_hora = int(G.input_temp[:n - 2])
    G.tmp_min = int(G.input_temp[n - 2:])
    if G.tmp_hora < 1 or G.tmp_hora > 12 or G.tmp_min > 59:
        linea(3, "Hora invalida!")
        time.sleep_ms(1200)
        linea(3, "#=OK  *=Borrar")
        G.input_temp = ""
        mostrar_entrada_hora()
        return False
    return True


def manejar_teclado(t):
    ab = t in ("A", "B")
    e = G.estado

    if e == PEDIR_DIA:
        if t == "C":
            G.mostrando_fin_semana = not G.mostrando_fin_semana
            mostrar_pantalla_dia()
        elif tecla_a_dia(t) >= 0:
            G.dia_actual = tecla_a_dia(t)
            pantalla("", centrar("Dia " + NOMBRES_DIAS[G.dia_actual]), centrar("seleccionado"))
            time.sleep_ms(1000)
            ir(PEDIR_HORA_ACTUAL)

    elif e == PEDIR_HORA_ACTUAL:
        if leer_hora(t):
            G.hora_actual, G.minuto_actual, G.segundo_actual = G.tmp_hora, G.tmp_min, 0
            ir(PEDIR_AMPMS_ACTUAL)

    elif e == PEDIR_AMPMS_ACTUAL:
        if ab:
            G.periodo_actual = "AM" if t == "A" else "PM"
            G.segundo_actual = 0
            G.t_reloj = ms()
            G.reloj_activo = True
            G.fase = FASE_NINGUNA
            G.horarios = [[] for _ in range(NUM_DIAS)]
            G.dia_config = 0
            ir(PEDIR_CANTIDAD)

    elif e == PEDIR_CANTIDAD:
        if leer_cantidad(t):
            G.cantidad_objetivo = G.tmp_cantidad
            ir(PEDIR_CONFIRMAR_CANTIDAD)

    elif e == PEDIR_CONFIRMAR_CANTIDAD:
        if t == "A":
            G.hora_config = 0
            if G.cantidad_objetivo == 0:
                avanzar_configuracion()
            else:
                ir(PEDIR_HORA_PASTA)
        elif t == "B":
            ir(PEDIR_CANTIDAD)

    elif e == PEDIR_HORA_PASTA:
        if leer_hora(t):
            ir(PEDIR_AMPM_PASTA)

    elif e == PEDIR_AMPM_PASTA:
        if ab:
            G.horarios[G.dia_config].append([G.tmp_hora, G.tmp_min, t == "B"])
            G.hora_config += 1
            if G.hora_config >= G.cantidad_objetivo:
                avanzar_configuracion()
            else:
                ir(PEDIR_HORA_PASTA)

    elif e == RELOJ_EN_VIVO:
        if G.fase == FASE_CONFIRMAR:
            if t == "#":
                mover_servo(ANGULO_ABIERTO)
                G.inicio_dispensado = ms()
                G.fase = FASE_DISPENSANDO
                actualizar_reloj_en_pantalla()
                registrar_toma()
        elif G.fase in (FASE_PEDIR_DEDO, FASE_MIDIENDO):
            if t == "C":
                G.resultado_bpm = G.resultado_spo2 = 0
                G.fase = FASE_CONFIRMAR
                actualizar_reloj_en_pantalla()
        elif G.fase == FASE_NINGUNA:
            if t == "D":
                G.mostrando_fin_semana = False
                ir(AJUSTAR_DIA)
            elif t == "*":
                G.reloj_activo = False
                G.mostrando_fin_semana = False
                ir(PEDIR_DIA)

    elif e == AJUSTAR_DIA:
        if t == "*":
            ir(RELOJ_EN_VIVO)
        elif t == "C":
            G.mostrando_fin_semana = not G.mostrando_fin_semana
            mostrar_pantalla_dia()
        elif t == "8" and G.mostrando_fin_semana:
            ir(AJUSTAR_RELOJ_HORA)
        elif tecla_a_dia(t) >= 0:
            G.dia_ajuste = tecla_a_dia(t)
            ir(AJUSTAR_INDICE)

    elif e == AJUSTAR_INDICE:
        lst = G.horarios[G.dia_ajuste]
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_DIA)
        elif t == "A":
            ir(AJUSTAR_AGREGAR_HORA)
        elif t == "B":
            if not lst:
                linea(3, "No hay que quitar")
                time.sleep_ms(1200)
                mostrar_pantalla()
            else:
                ir(AJUSTAR_BORRAR)
        elif entrada(t, 3, mostrar_entrada_indice) and G.input_temp:
            n = int(G.input_temp)
            if 1 <= n <= len(lst):
                G.idx_ajuste = n - 1
                ir(AJUSTAR_HORA)
            else:
                linea(3, "Numero invalido!")
                time.sleep_ms(1200)
                G.input_temp = ""
                mostrar_pantalla()

    elif e == AJUSTAR_HORA:
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_INDICE)
        elif leer_hora(t):
            ir(AJUSTAR_AMPM)

    elif e == AJUSTAR_AMPM:
        if ab:
            h = G.horarios[G.dia_ajuste][G.idx_ajuste]
            h[0], h[1], h[2] = G.tmp_hora, G.tmp_min, (t == "B")
            pantalla("", "Horario cambiado!", texto_horario(h[0], h[1], h[2]))
            time.sleep_ms(1500)
            ir(RELOJ_EN_VIVO)
        elif t == "*":
            ir(AJUSTAR_HORA)

    elif e == AJUSTAR_RELOJ_HORA:
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_DIA)
        elif leer_hora(t):
            ir(AJUSTAR_RELOJ_AMPM)

    elif e == AJUSTAR_RELOJ_AMPM:
        if ab:
            pm = (t == "B")
            pantalla("", "Hora cambiada!", texto_horario(G.tmp_hora, G.tmp_min, pm))
            time.sleep_ms(1500)
            G.hora_actual, G.minuto_actual, G.segundo_actual = G.tmp_hora, G.tmp_min, 0
            G.periodo_actual = "PM" if pm else "AM"
            G.t_reloj = ms()
            ir(RELOJ_EN_VIVO)
        elif t == "*":
            ir(AJUSTAR_RELOJ_HORA)

    elif e == AJUSTAR_AGREGAR_HORA:
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_INDICE)
        elif leer_hora(t):
            ir(AJUSTAR_AGREGAR_AMPM)

    elif e == AJUSTAR_AGREGAR_AMPM:
        if ab:
            G.horarios[G.dia_ajuste].append([G.tmp_hora, G.tmp_min, t == "B"])
            pantalla("", "Horario agregado!", texto_horario(G.tmp_hora, G.tmp_min, t == "B"))
            time.sleep_ms(1500)
            ir(AJUSTAR_INDICE)
        elif t == "*":
            ir(AJUSTAR_AGREGAR_HORA)

    elif e == AJUSTAR_BORRAR:
        lst = G.horarios[G.dia_ajuste]
        if t == "*" and not G.input_temp:
            ir(AJUSTAR_INDICE)
        elif entrada(t, 3, mostrar_entrada_indice) and G.input_temp:
            n = int(G.input_temp)
            if 1 <= n <= len(lst):
                h = lst.pop(n - 1)
                pantalla("", "Horario borrado!", texto_horario(h[0], h[1], h[2]))
                time.sleep_ms(1500)
                ir(AJUSTAR_INDICE)
            else:
                linea(3, "Numero invalido!")
                time.sleep_ms(1200)
                G.input_temp = ""
                mostrar_pantalla()


# ==========================================================
#  PROGRAMA PRINCIPAL
# ==========================================================
def main():
    global sensor, sensor_ok
    mover_servo(ANGULO_CERRADO)

    try:
        sensor = MAX30102(i2c)
        sensor_ok = True
        print("MAX30102 listo.")
    except Exception as ex:
        print("MAX30102 NO detectado. Se omitira la medicion.", ex)
        pantalla("", "Sensor de pulso", "NO detectado")
        time.sleep_ms(2000)

    conectar_wifi()
    mostrar_pantalla()

    while True:
        avanzar_reloj()
        revisar_proximidad()
        procesar_sensor_pulso()
        manejar_resultado()
        manejar_servo()
        manejar_buzzer()
        manejar_motor()
        revisar_alertas()

        t = leer_tecla()
        if t:
            manejar_teclado(t)


main()

    conectar_wifi()
    mostrar_pantalla()

    while True:
        avanzar_reloj()
        revisar_proximidad()
        procesar_sensor_pulso()
        manejar_resultado()
        manejar_servo()
        manejar_buzzer()
        manejar_motor()
        revisar_alertas()

        t = leer_tecla()
        if t:
            manejar_teclado(t)


main()
