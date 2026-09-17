"""Backend API de GuateAyuda (Flask).

Expone endpoints JSON que el frontend (templates/static) consumirá. Integra:

    * db.py                -> acceso a datos (el esquema lo define el compañero de bd)
    * analytics/engine.py  -> motor analítico / indicadores
    * interpreter.py       -> Chat IA: lenguaje natural -> estructura
    * service.py           -> guardar operaciones confirmadas

El backend está diseñado para funcionar cuando el esquema (`bd/schema.sql`) y el
listener de PostgreSQL estén listos. Si la base no está disponible, devuelve
errores JSON claros en vez de fallar en silencio.

Uso:
    python app.py
"""

from flask import Flask, jsonify, render_template, request, session, redirect, url_for, g, send_file
import functools
import html
import io
import os
import re
from datetime import datetime

# ReportLab para el reporte PDF detallado multi-página.
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.textlabels import Label
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


import db
from analytics import (
    estado_motor,
    gastos_por_dia,
    indicadores_principales,
    inventario_bajo,
    perfil_productivo,
    productos_de_negocio,
    proyeccion_ml,
    proyeccion_ventas_futuras,
    tendencia_ventas,
    top_productos,
    ventas_por_dia,
)
from ml.anomaly import detectar_anomalias
from ml.forecasting import pronostico_negocio
from ml.inventory import analisis_inventario
from ml.recommendations import (
    generar_recomendaciones,
    registrar_recomendaciones,
)
import interpreter
import service

app = Flask(__name__)
# En producción usar variable de entorno SECRET_KEY; fallback para desarrollo.
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")


@app.after_request
def _sin_cache_en_static(response):
    """Fase de pruebas: evita que el navegador use CSS/JS en caché."""
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def negocio_existe(negocio_id):
    return db.query_one("SELECT id FROM negocio WHERE id = %s", (negocio_id,))


def _bd_error(exc):
    return jsonify({"error": "base_de_datos_no_disponible",
                    "mensaje": f"No se pudo conectar a la base de datos: {exc}",
                    "detalle": "El esquema (bd/schema.sql) y PostgreSQL deben estar listos."}), 503


def _no_encontrado(mensaje="Negocio no encontrado."):
    return jsonify({"error": "no_encontrado", "mensaje": mensaje}), 404


def _consulta(tipo, mensaje, datos=None):
    """Respuesta de una consulta del asesor virtual."""
    return {
        "interpretado": True,
        "consulta": True,
        "tipo": tipo,
        "mensaje": mensaje,
        "datos": datos or [],
    }


def _formato_q(monto):
    try:
        return f"Q{float(monto or 0):,.2f}"
    except (TypeError, ValueError):
        return "Q0.00"


# ---------------------------------------------------------------------------
# Respuestas de inteligencia (FASE 7): chat conectado al motor ML
# ---------------------------------------------------------------------------

def _respuesta_prediccion(negocio_id):
    """Responde a una consulta de predicción con los datos del motor ML."""
    dias = 7
    try:
        proy = pronostico_negocio(negocio_id, dias)
    except Exception:
        proy = {}
    if not proy.get("disponible"):
        return _consulta(
            "prediccion",
            proy.get("mensaje", "No hay suficientes datos para predecir tus ventas."),
            datos=[],
        )
    total = sum(float(p.get("estimado") or 0) for p in proy.get("predicciones", []))
    estado = proy.get("estado") or "fallback_estadistico"
    etiqueta_metodo = {
        "modelo_ml": "modelo estadístico (ML)",
        "mixto": "modelo mixto",
        "fallback_estadistico": "promedio histórico",
    }.get(estado, "promedio histórico")
    mensaje = (
        f"Se estiman ventas de {_formato_q(total)} en los próximos {dias} días "
        f"({etiqueta_metodo}). Es una estimación, no una certeza."
    )
    datos = [
        {"etiqueta": "Ventas estimadas (7 días)", "valor": _formato_q(total)},
        {"etiqueta": "Método", "valor": etiqueta_metodo.capitalize()},
        {"etiqueta": "Estado", "valor": estado},
    ]
    return _consulta("prediccion", mensaje, datos=datos)


def _respuesta_inventario_riesgo(negocio_id):
    """Responde con los productos en riesgo de agotamiento."""
    dias = 7
    analisis = analisis_inventario(negocio_id, dias)
    en_riesgo = analisis.get("en_riesgo", [])
    if not en_riesgo:
        return _consulta(
            "inventario_riesgo",
            "No se detectaron productos en riesgo de agotarse en los próximos "
            f"{dias} días.",
            datos=[],
        )
    nombres = ", ".join(p["producto"] for p in en_riesgo[:5])
    mensaje = (
        f"Hay {len(en_riesgo)} producto(s) con riesgo de quedarte sin stock en "
        f"los próximos {dias} días: {nombres}. La reposición es solo una "
        "sugerencia (no se realiza ninguna compra automática)."
    )
    datos = [
        {
            "etiqueta": p["producto"],
            "valor": (f"{p.get('dias_hasta_agotamiento')} días · "
                      f"riesgo {p.get('riesgo')} · reponer ≈ "
                      f"{p.get('reposicion_sugerida')} u."),
        }
        for p in en_riesgo
    ]
    return _consulta("inventario_riesgo", mensaje, datos=datos)


def _respuesta_anomalias(negocio_id):
    """Responde con los comportamientos inusuales detectados."""
    deteccion = detectar_anomalias(negocio_id, 60)
    tot = deteccion.get("total_anomalias", 0)
    areas = deteccion.get("areas", {})
    todas = [
        dict(a, area=area)
        for area, bloque in areas.items()
        for a in bloque.get("anomalias", [])
    ]
    if not tot or not todas:
        return _consulta(
            "anomalias",
            deteccion.get("mensaje",
                          "No se detectaron comportamientos inusuales en el "
                          "periodo revisado."),
            datos=[],
        )
    mensaje = (
        f"Se detectaron {tot} comportamiento(s) que requieren revisión. "
        "No se concluye fraude ni error: solo son datos fuera del patrón "
        "habitual."
    )
    datos = [
        {
            "etiqueta": f"{a.get('area', '')} · {a.get('fecha')}",
            "valor": (f"{a.get('desviacion_porcentual', 0):.1f}% "
                      f"{'más' if a.get('direccion') == 'alta' else 'menos'} "
                      f"de lo habitual · revisar"),
        }
        for a in todas[:6]
    ]
    return _consulta("anomalias", mensaje, datos=datos)


def _respuesta_recomendaciones(negocio_id):
    """Responde con las recomendaciones accionables del negocio."""
    dias = 7
    resultado = generar_recomendaciones(negocio_id, dias)
    recomendaciones = resultado.get("recomendaciones", [])
    if not recomendaciones:
        return _consulta(
            "recomendaciones",
            "Todo se ve dentro del patrón habitual del negocio. No hay "
            "recomendaciones urgentes por ahora.",
            datos=[],
        )
    mensaje = (
        f"Te dejo {len(recomendaciones)} recomendación(es) basadas en datos "
        "reales del negocio (estimaciones, no certezas)."
    )
    datos = [
        {
            "etiqueta": r["titulo"],
            "valor": f"[{r.get('prioridad')}] {r.get('accion_sugerida', '')}",
        }
        for r in recomendaciones
    ]
    return _consulta("recomendaciones", mensaje, datos=datos)


def _respuesta_consulta(negocio_id, resultado):
    """Construye la respuesta del asesor para una consulta del usuario."""
    intencion = resultado.get("tipo") or resultado.get("intencion") or "ayuda"

    try:
        if intencion == "saludo":
            return _consulta(
                "saludo",
                "¡Hola! Soy tu asesor virtual de GuateAyuda. Puedo registrar tus "
                "operaciones y responder preguntas sobre tu negocio. Prueba con:\n"
                "• 'Vendí 8 almuerzos a Q25' (registrar)\n"
                "• '¿Qué productos tengo?'\n"
                "• '¿Cómo van mis ventas?'\n"
                "• 'Dame un resumen'.",
            )

        if intencion == "asesor":
            return _consulta(
                "asesor",
                "Soy el asesor virtual de GuateAyuda, creado por el Equipo Quetzalito "
                "para la Hackathon FIT 2026. Registro tus operaciones del día y "
                "respondo preguntas sobre tu negocio: productos, ventas, gastos, "
                "inventario y un resumen general.",
            )

        if intencion == "despedida":
            return _consulta(
                "despedida",
                "¡Con gusto! Aquí estaré cuando necesites registrar o consultar algo "
                "de tu negocio. ¡Éxitos!",
            )

        if intencion == "ayuda":
            return _consulta(
                "ayuda",
                "Puedo ayudarte de dos formas:\n"
                "1) Registrar operaciones: 'Vendí 8 almuerzos a Q25', "
                "'Gasté Q150 comprando verduras', 'Me quedan 10 gaseosas', "
                "'Se fabricaron 24 unidades de vasos'.\n"
                "2) Consultar tu negocio: '¿Qué productos tengo?', "
                "'¿Cuánto he vendido?', '¿Qué me queda?', 'Dame un resumen'.",
            )

        if intencion == "productos":
            datos = productos_de_negocio(negocio_id)
            if not datos:
                return _consulta(
                    "productos",
                    "Aún no tienes productos registrados. Puedes registrar "
                    "inventario con un mensaje como 'Me quedan 10 gaseosas'.",
                )
            nombres = ", ".join(d["producto"] for d in datos)
            return _consulta(
                "productos",
                f"Tienes {len(datos)} producto(s) registrado(s):\n{nombres}.",
                datos=datos,
            )

        if intencion == "ventas":
            ind = indicadores_principales(negocio_id)
            tendencia = tendencia_ventas(negocio_id)
            texto = f"Tus ventas registradas suman {_formato_q(ind['ventas_registradas'])}."
            if tendencia.get("disponible"):
                texto += f" {tendencia.get('mensaje')}"
            return _consulta(
                "ventas",
                texto,
                datos=[
                    {"etiqueta": "Ventas registradas", "valor": _formato_q(ind["ventas_registradas"])},
                    {"etiqueta": "Número de operaciones", "valor": str(ind.get("numero_operaciones") or 0)},
                    {"etiqueta": "Productos activos", "valor": str(ind.get("productos_activos") or 0)},
                ],
            )

        if intencion == "gastos":
            ind = indicadores_principales(negocio_id)
            return _consulta(
                "gastos",
                f"Tus gastos registrados suman {_formato_q(ind['gastos_registrados'])}.",
                datos=[
                    {"etiqueta": "Gastos registrados", "valor": _formato_q(ind["gastos_registrados"])},
                    {"etiqueta": "Número de operaciones", "valor": str(ind.get("numero_operaciones") or 0)},
                ],
            )

        if intencion == "inventario":
            datos = productos_de_negocio(negocio_id)
            if not datos:
                return _consulta(
                    "inventario",
                    "Aún no tienes productos con inventario registrado.",
                )
            bajos = [d for d in datos
                     if float(d.get("existencia") or 0) <= float(d.get("minimo") or 0)]
            if bajos:
                nombres = ", ".join(d["producto"] for d in bajos)
                mensaje = (f"De tus {len(datos)} producto(s), estos tienen inventario "
                           f"bajo o agotado: {nombres}.")
            else:
                mensaje = "Tus productos están con un nivel de inventario adecuado."
            return _consulta("inventario", mensaje, datos=datos)

        if intencion == "resumen":
            perfil = perfil_productivo(negocio_id)
            ind = indicadores_principales(negocio_id)
            nombre = perfil.get("negocio", "Tu negocio")
            return _consulta(
                "resumen",
                f"{nombre} · {perfil.get('operaciones', 0)} operación(es) registrada(s).",
                datos=[
                    {"etiqueta": "Ventas registradas", "valor": _formato_q(ind["ventas_registradas"])},
                    {"etiqueta": "Gastos registrados", "valor": _formato_q(ind["gastos_registrados"])},
                    {"etiqueta": "Número de operaciones", "valor": str(ind.get("numero_operaciones") or 0)},
                    {"etiqueta": "Productos activos", "valor": str(ind.get("productos_activos") or 0)},
                ],
            )

        if intencion == "prediccion":
            return _respuesta_prediccion(negocio_id)

        if intencion == "inventario_riesgo":
            return _respuesta_inventario_riesgo(negocio_id)

        if intencion == "anomalias":
            return _respuesta_anomalias(negocio_id)

        if intencion == "recomendaciones":
            return _respuesta_recomendaciones(negocio_id)

    except Exception:
        return _consulta(intencion, "No pude consultar tus datos en este momento. Inténtalo de nuevo.")

    return _consulta(intencion, "No entiendo esa consulta. Escribe 'ayuda' para ver opciones.")


# ---------------------------------------------------------------------------
# Infraestructura
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")

# ---------------------------------------------------------------------------
# Autenticación y Registro
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Simulación simple de login
        session["user_id"] = 1
        session["negocio_id"] = 1
        return redirect(url_for("dashboard_view"))
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        propietario = request.form.get("propietario")
        actividad = request.form.get("actividad_principal")
        descripcion = request.form.get("descripcion")
        depto = request.form.get("departamento")
        mun = request.form.get("municipio")
        
        # Insertar negocio
        db.execute(
            "INSERT INTO negocio (nombre, propietario, actividad_principal, descripcion, departamento, municipio) VALUES (%s, %s, %s, %s, %s, %s)",
            (nombre, propietario, actividad, descripcion, depto, mun)
        )
        
        # Obtener el ID del negocio recién insertado
        fila = db.query_one("SELECT id FROM negocio WHERE nombre = %s ORDER BY creado_en DESC LIMIT 1", (nombre,))
        negocio_id = fila["id"]
        
        session["user_id"] = 1 # Simulación de usuario
        session["negocio_id"] = negocio_id
        return redirect(url_for("dashboard_view"))
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/empresa/configuracion", methods=["GET", "POST"])
@login_required
def configuracion_empresa():
    negocio_id = session.get("negocio_id")
    negocio = db.query_one("SELECT * FROM negocio WHERE id = %s", (negocio_id,))
    return render_template("configuracion.html", negocio=negocio)


@app.get("/dashboard")
@login_required
def dashboard_view():
    negocio_id = session.get("negocio_id")
    negocio = db.query_one("SELECT * FROM negocio WHERE id = %s", (negocio_id,))
    return render_template("dashboard.html", negocio=negocio)


@app.get("/chat")
@login_required
def chat_view():
    return render_template("chat.html")



COLOR_AZUL = colors.HexColor("#0B5FA5")
COLOR_VERDE = colors.HexColor("#1E7B34")
COLOR_ROJO = colors.HexColor("#C0392B")
COLOR_GRIS = colors.HexColor("#5B6472")
COLOR_FONDO = colors.HexColor("#EEF2F7")
COLOR_BORDE = colors.HexColor("#C8D2E0")
COLOR_CLARO = colors.HexColor("#F8FAFD")


def _esc(texto):
    """Escapa texto plano para usarlo dentro de un Paragraph de ReportLab."""
    return html.escape(str(texto or ""))


def _fmt_q(valor):
    """Formatea un número como moneda: Q1,234.56 (formato guatemalteco)."""
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        v = 0.0
    return "Q{:,.2f}".format(v).replace(",", "~").replace(".", ",").replace("~", ".")


def _fmt_num(valor):
    """Formatea un número sin decimales innecesarios: 40 / 12.5."""
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        v = 0
    return "{:,.0f}".format(v) if v == int(v) else "{:,.1f}".format(v)


def _fmt_fecha(cadena):
    """Convierte '2026-08-28 ...' a '28/08/2026'."""
    if not cadena:
        return "—"
    txt = str(cadena)[:10]
    partes = txt.split("-")
    if len(partes) == 3 and partes[0].isdigit():
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return txt


def _slug(texto):
    t = re.sub(r"[^\w]+", "-", (texto or "").strip().lower()).strip("-")
    return t or "negocio"


def _estilos_pdf():
    base = ParagraphStyle(
        "base", fontName="Helvetica", fontSize=9.5, leading=13,
        textColor=colors.HexColor("#1F2833"),
    )
    return {
        "titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold",
                                 fontSize=17, leading=21, textColor=COLOR_AZUL, spaceAfter=2),
        "marca": ParagraphStyle("marca", parent=base, fontName="Helvetica-Bold",
                                fontSize=8.5, leading=11, textColor=colors.white),
        "cabecera_meta": ParagraphStyle("cabecera_meta", parent=base, fontSize=8,
                                        leading=11, textColor=colors.white),
        "nombre_negocio": ParagraphStyle("nombre_negocio", parent=base,
                                         fontName="Helvetica-Bold", fontSize=13,
                                         leading=16, textColor=colors.HexColor("#10243C")),
        "subtitulo": ParagraphStyle("subtitulo", parent=base, fontSize=10,
                                    leading=14, textColor=COLOR_GRIS),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11.5,
                             leading=15, textColor=COLOR_AZUL, spaceBefore=14, spaceAfter=3),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=9,
                             leading=12, textColor=COLOR_GRIS, spaceBefore=8, spaceAfter=2),
        "nota": ParagraphStyle("nota", parent=base, fontSize=8, leading=10.5,
                               textColor=COLOR_GRIS, spaceBefore=4),
        "vacio": ParagraphStyle("vacio", parent=base, italic=True, fontSize=9,
                                textColor=COLOR_GRIS, spaceBefore=2),
        "celda": ParagraphStyle("celda", parent=base, fontSize=8.5, leading=11),
        "celda_bold": ParagraphStyle("celda_bold", parent=base, fontName="Helvetica-Bold",
                                     fontSize=8.5, leading=11),
        "kpi": ParagraphStyle("kpi", parent=base, fontSize=8, leading=10,
                              textColor=COLOR_GRIS, alignment=TA_CENTER),
    }


def _pie_de_pagina(hoja, doc):
    """Pinta la franja inferior con la fecha de generación y el número de página."""
    hoja.saveState()
    hoja.setFont("Helvetica", 7.5)
    hoja.setFillColor(COLOR_GRIS)
    hoja.drawString(
        1.6 * cm, 1.0 * cm,
        "Generado por GuateAyuda — Equipo Quetzalito (Hackathon FIT 2026) · Fase de pruebas",
    )
    hoja.drawRightString(letter[0] - 1.6 * cm, 1.0 * cm, f"Página {doc.page}")
    hoja.restoreState()


def _seccion_titulo(texto, estilos):
    return [
        Paragraph(texto, estilos["h2"]),
        HRFlowable(width="100%", thickness=0.7, color=COLOR_BORDE, spaceAfter=6),
    ]


def _encabezado(negocio, estilos):
    """Bloque superior: marca, fecha de generación y datos del negocio."""
    ahora = datetime.now()
    cab = Table(
        [[
            Paragraph("GUATEAYUDA&nbsp;&nbsp;·&nbsp;&nbsp;Reporte de Negocio",
                      estilos["marca"]),
            Paragraph(f"Generado el {ahora.strftime('%d/%m/%Y')} a las "
                      f"{ahora.strftime('%H:%M')} · Fase de pruebas",
                      estilos["cabecera_meta"]),
        ]],
        colWidths=[11 * cm, 7 * cm],
    )
    cab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_AZUL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (0, 0), 14),
        ("LEFTPADDING", (1, 0), (1, 0), 4),
        ("RIGHTPADDING", (0, 0), (0, 0), 4),
        ("RIGHTPADDING", (1, 0), (1, 0), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))

    nombre = (negocio or {}).get("nombre") or "Mi Negocio"
    celdas = [Paragraph(_esc(nombre), estilos["nombre_negocio"])]
    if (negocio or {}).get("propietario"):
        celdas.append(Paragraph(f"Propietario/a: {_esc((negocio or {}).get('propietario'))}",
                                estilos["subtitulo"]))
    act = (negocio or {}).get("actividad") or (negocio or {}).get("actividad_principal")
    if act:
        celdas.append(Paragraph(f"Actividad: {_esc(act)}", estilos["subtitulo"]))
    ub = " · ".join(x for x in [
        (negocio or {}).get("municipio") or "",
        (negocio or {}).get("departamento") or "",
    ] if x)
    if ub:
        celdas.append(Paragraph(f"Ubicación: {_esc(ub)}", estilos["subtitulo"]))
    if (negocio or {}).get("descripcion"):
        celdas.append(Paragraph(_esc((negocio or {}).get("descripcion")), estilos["nota"]))

    bloque = Table([[c] for c in celdas])
    bloque.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, -1), (-1, -1), 1, COLOR_BORDE),
    ]))
    return [cab, Spacer(1, 6), bloque]


def _seccion_kpis(ind, estilos):
    """Cuatro tarjetas de resumen: ventas, gastos, operaciones, productos."""
    kpis = [
        ("Ventas Registradas", _fmt_q(ind["ventas_registradas"]), "#1E7B34"),
        ("Gastos Registrados", _fmt_q(ind["gastos_registrados"]), "#C0392B"),
        ("Operaciones", _fmt_num(ind["numero_operaciones"]), "#0B5FA5"),
        ("Productos Activos", _fmt_num(ind["productos_activos"]), "#5B6472"),
    ]
    fila = []
    for i, (label, valor, hex_color) in enumerate(kpis):
        celda = Paragraph(
            f'<font color="{hex_color}"><b>{_esc(valor)}</b></font>'
            f'<br/><font size="7.5" color="#5B6472">{_esc(label)}</font>',
            estilos["kpi"],
        )
        fila.append(celda)
    t = Table([fila], colWidths=[4.5 * cm] * 4)
    estilos_tabla = [
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, COLOR_BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]
    for i in range(4):
        estilos_tabla.append(("LINEABOVE", (i, 0), (i, 0), 2.5, colors.HexColor(kpis[i][2])))
    t.setStyle(TableStyle(estilos_tabla))
    return [Paragraph("RESUMEN EJECUTIVO", estilos["h2"]), KeepTogether([t, Spacer(1, 6)])]


def _tabla_base(filas_encabezado, cuerpo, anchos, estilos, alineaciones=None):
    """Construye una tabla estilizada con encabezado repetible."""
    datos = [filas_encabezado] + cuerpo
    t = Table(datos, colWidths=anchos, repeatRows=1)
    estilos_tabla = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_FONDO),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_CLARO]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if alineaciones:
        for (col, inicio, fin, alineacion) in alineaciones:
            estilos_tabla.append(("ALIGN", (col, inicio), (col, fin), alineacion))
    t.setStyle(TableStyle(estilos_tabla))
    return t


def _filas_top_productos(top, estilos):
    filas = []
    for f in top:
        filas.append([
            Paragraph(_esc(f["producto"]), estilos["celda"]),
            Paragraph(_fmt_num(f["unidades"]), estilos["celda"]),
            Paragraph(_fmt_q(f["ingresos"]), estilos["celda"]),
        ])
    return filas


def _tabla_top_productos(top, estilos):
    enc = [
        Paragraph("Producto", estilos["celda_bold"]),
        Paragraph("Unidades", estilos["celda_bold"]),
        Paragraph("Ingresos", estilos["celda_bold"]),
    ]
    t = _tabla_base(enc, _filas_top_productos(top, estilos),
                    [8 * cm, 4 * cm, 5 * cm], estilos,
                    alineaciones=[(1, 1, -1, "CENTER"), (2, 1, -1, "RIGHT")])
    return KeepTogether([
        Paragraph("Productos con mayores ingresos del periodo registrado.", estilos["h3"]),
        t,
    ])


def _filas_inventario(inventario, bajos, estilos):
    filas = []
    for f in inventario:
        bajo = f["producto"].lower() in bajos
        estado = "STOCK BAJO" if bajo else "OK"
        estado_html = (f'<font color="#C0392B"><b>{estado}</b></font>' if bajo
                       else f'<font color="#1E7B34">{estado}</font>')
        filas.append([
            Paragraph(_esc(f["producto"]), estilos["celda"]),
            Paragraph(_fmt_q(f["precio"]), estilos["celda"]),
            Paragraph(_fmt_num(f["existencia"]), estilos["celda"]),
            Paragraph(_fmt_num(f["minimo"]), estilos["celda"]),
            Paragraph(estado_html, estilos["celda"]),
        ])
    return filas


def _tabla_inventario(inventario, bajos, estilos):
    enc = [
        Paragraph("Producto", estilos["celda_bold"]),
        Paragraph("Precio ref.", estilos["celda_bold"]),
        Paragraph("Existencia", estilos["celda_bold"]),
        Paragraph("Mínimo", estilos["celda_bold"]),
        Paragraph("Estado", estilos["celda_bold"]),
    ]
    t = _tabla_base(enc, _filas_inventario(inventario, bajos, estilos),
                    [6 * cm, 3 * cm, 2.8 * cm, 2.2 * cm, 3.2 * cm], estilos,
                    alineaciones=[(1, 1, -1, "RIGHT"), (2, 1, -1, "CENTER"),
                                  (3, 1, -1, "CENTER"), (4, 1, -1, "CENTER")])
    return KeepTogether([
        Paragraph(f"{len(inventario)} producto(s) registrado(s). En rojo, los que "
                  "están por debajo o igual al mínimo.", estilos["h3"]),
        t,
    ])


def _filas_movimientos(movimientos, estilos):
    filas = []
    for f in movimientos:
        tipo = str(f.get("tipo") or "—").upper()
        color = "#1E7B34" if "VENTA" in tipo else "#C0392B" if tipo == "GASTO" else "#5B6472"
        concepto = f.get("descripcion") or f.get("origen") or "—"
        filas.append([
            Paragraph(_fmt_fecha(f.get("fecha")), estilos["celda"]),
            Paragraph(f'<font color="{color}"><b>{_esc(tipo)}</b></font>', estilos["celda"]),
            Paragraph(_esc(concepto), estilos["celda"]),
            Paragraph(_fmt_q(f.get("monto")), estilos["celda"]),
        ])
    return filas


def _tabla_movimientos(movimientos, estilos):
    enc = [
        Paragraph("Fecha", estilos["celda_bold"]),
        Paragraph("Tipo", estilos["celda_bold"]),
        Paragraph("Concepto", estilos["celda_bold"]),
        Paragraph("Monto", estilos["celda_bold"]),
    ]
    t = _tabla_base(enc, _filas_movimientos(movimientos, estilos),
                    [2.6 * cm, 2.4 * cm, 8 * cm, 4.2 * cm], estilos,
                    alineaciones=[(0, 1, 0, "CENTER"), (1, 1, 1, "CENTER"),
                                  (3, 1, 3, "RIGHT")])
    return KeepTogether([
        Paragraph("Los 15 movimientos registrados más recientes.", estilos["h3"]),
        t,
    ])


def _texto_tendencia(tendencia, estilos):
    if not tendencia.get("disponible"):
        return [Paragraph(_esc(tendencia.get("mensaje") or
                               "No hay suficiente historial para calcular una tendencia."),
                          estilos["vacio"])]
    cambio = tendencia.get("cambio_porcentual")
    color = "#1E7B34" if (cambio or 0) >= 0 else "#C0392B"
    signo = "+" if (cambio or 0) >= 0 else ""
    return [
        Paragraph("Comparación entre los dos últimos periodos de 7 días con ventas.",
                  estilos["h3"]),
        Paragraph(
            f'<font size="15" color="{color}"><b>{signo}{_fmt_num(cambio)}%</b></font> '
            f'<font size="8" color="#5B6472">{_esc(tendencia.get("mensaje") or "")}</font>',
            estilos["celda"],
        ),
        Spacer(1, 4),
    ]


def _tabla_proyeccion(proyeccion, estilos):
    if not proyeccion.get("disponible"):
        return [Paragraph(_esc(proyeccion.get("mensaje") or
                               "Sin historial suficiente para proyectar."),
                          estilos["vacio"])]
    filas = []
    for f in proyeccion["proyeccion"]:
        filas.append([
            Paragraph(_fmt_fecha(f["dia"]), estilos["celda"]),
            Paragraph(_fmt_q(f["estimado"]), estilos["celda"]),
        ])
    enc = [
        Paragraph("Día estimado", estilos["celda_bold"]),
        Paragraph("Ventas estimadas", estilos["celda_bold"]),
    ]
    t = _tabla_base(enc, filas, [6 * cm, 6 * cm], estilos,
                    alineaciones=[(1, 1, -1, "RIGHT")])
    nota = (f"Base diaria usada: {_fmt_q(proyeccion.get('base_diaria'))} "
            f"(media móvil de los últimos periodos con ventas). "
            f"Método: {proyeccion.get('metodo', 'media_movil_simple')}. "
            "Proyección bajo hipótesis: es una estimación por reglas, NO una "
            "predicción de un modelo (sección 23 del contexto).")
    return KeepTogether([
        Paragraph(f"Estimación para los próximos {proyeccion.get('periodo_dias', 7)} días.",
                  estilos["h3"]),
        t,
        Paragraph(nota, estilos["nota"]),
    ])


def _grafico_ventas_diarias(serie, estilos):
    """Gráfico de barras vectorial de ventas por día (no requiere matplotlib)."""
    if not serie:
        return [Paragraph("Sin datos de ventas por día para graficar todavía.",
                          estilos["vacio"])]
    montos = [max(float(f["total"] or 0), 0) for f in serie]
    dias = [str(f["dia"])[5:10] for f in serie]

    ancho = 17.2 * cm
    alto = 5.8 * cm
    dibujo = Drawing(ancho, alto)

    grafico = VerticalBarChart()
    grafico.x = 52
    grafico.y = 30
    grafico.width = ancho - 62
    grafico.height = alto - 54
    grafico.data = [montos]
    grafico.categoryAxis.categoryNames = dias
    grafico.bars[0].fillColor = COLOR_AZUL
    if len(dias) > 12:
        grafico.categoryAxis.labels.visible = False
    else:
        grafico.categoryAxis.labels.fontName = "Helvetica"
        grafico.categoryAxis.labels.fontSize = 6
        grafico.categoryAxis.labels.fillColor = COLOR_GRIS
    maximo = max(montos)
    if maximo > 0:
        grafico.valueAxis.valueMin = 0
        grafico.valueAxis.valueMax = maximo * 1.15
        grafico.valueAxis.valueStep = maximo * 0.15
        grafico.valueAxis.labels.fontName = "Helvetica"
        grafico.valueAxis.labels.fontSize = 6
        grafico.valueAxis.labels.fillColor = COLOR_GRIS
    dibujo.add(grafico)

    etiqueta_y = Label()
    etiqueta_y.setOrigin(12, alto / 2)
    etiqueta_y.angle = 90
    etiqueta_y.setText("Q")
    etiqueta_y.fontName = "Helvetica"
    etiqueta_y.fontSize = 7
    etiqueta_y.fillColor = COLOR_GRIS
    dibujo.add(etiqueta_y)

    return [
        Paragraph(f"Ventas diarias en los últimos {len(montos)} día(s) con registros.",
                  estilos["h3"]),
        dibujo,
    ]


def _generar_reporte_pdf(negocio_id):
    """Construye el reporte PDF detallado → (io.BytesIO, nombre_archivo)."""
    negocio = db.query_one("SELECT * FROM negocio WHERE id = %s", (negocio_id,))
    estilos = _estilos_pdf()

    ind = indicadores_principales(negocio_id)
    top = top_productos(negocio_id, n=5)
    inventario = productos_de_negocio(negocio_id)
    bajos = {f["producto"].lower() for f in inventario_bajo(negocio_id)}
    tendencia = tendencia_ventas(negocio_id)
    proyeccion = proyeccion_ventas_futuras(negocio_id, dias=7)
    serie = ventas_por_dia(negocio_id, dias=30)
    movimientos = db.query(
        "SELECT fecha, tipo, descripcion, monto, origen FROM transaccion "
        "WHERE negocio_id = %s ORDER BY fecha DESC, id DESC LIMIT 15",
        (negocio_id,),
    )

    story = []
    story += _encabezado(negocio, estilos)
    story.append(Spacer(1, 4))
    story += _seccion_kpis(ind, estilos)
    story += _seccion_titulo("Top de Productos", estilos)
    if top:
        story.append(_tabla_top_productos(top, estilos))
    else:
        story.append(Paragraph("Sin ventas registradas todavía.", estilos["vacio"]))
    story += _seccion_titulo("Inventario", estilos)
    if inventario:
        story.append(_tabla_inventario(inventario, bajos, estilos))
    else:
        story.append(Paragraph("Sin productos registrados.", estilos["vacio"]))
    story += _seccion_titulo("Últimos Movimientos", estilos)
    if movimientos:
        story.append(_tabla_movimientos(movimientos, estilos))
    else:
        story.append(Paragraph("Sin movimientos registrados todavía.", estilos["vacio"]))

    story.append(PageBreak())
    story += _seccion_titulo("Ventas por Día (últimos 30 días)", estilos)
    story += _grafico_ventas_diarias(serie, estilos)
    story += _seccion_titulo("Tendencia de Ventas", estilos)
    story += _texto_tendencia(tendencia, estilos)
    story += _seccion_titulo("Proyección a 7 Días", estilos)
    story += _tabla_proyeccion(proyeccion, estilos)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.6 * cm,
        title=f"Reporte - {(negocio or {}).get('nombre') or 'Mi Negocio'}",
        author="GuateAyuda (Equipo Quetzalito)",
    )
    doc.build(story, onFirstPage=_pie_de_pagina, onLaterPages=_pie_de_pagina)
    nombre = _slug((negocio or {}).get("nombre"))
    return buffer, nombre


@app.get("/reportes")
@login_required
def generar_reporte():
    negocio_id = session.get("negocio_id")
    if not negocio_id:
        return redirect(url_for("login"))

    buffer, nombre = _generar_reporte_pdf(negocio_id)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"reporte-{nombre}.pdf",
        mimetype="application/pdf",
    )




@app.get("/api")
def api_index():
    return jsonify({
        "api": "GuateAyuda Backend",
        "version": "1.0",
        "endpoints": [
            "GET /api/negocios",
            "GET /api/negocio/<id>",
            "GET /api/negocio/<id>/dashboard",
            "GET /api/negocio/<id>/ventas-por-dia?dias=N",
            "GET /api/negocio/<id>/gastos-por-dia?dias=N",
            "GET /api/negocio/<id>/top-productos?n=N",
            "GET /api/negocio/<id>/inventario-bajo",
            "GET /api/negocio/<id>/tendencia",
            "GET /api/negocio/<id>/perfil",
            "GET /api/negocio/<id>/proyeccion?dias=N",
            "GET /api/negocio/<id>/prediccion?dias=N",
            "GET /api/negocio/<id>/inventario-predictivo?dias=N",
            "GET /api/negocio/<id>/anomalias?dias=N",
            "GET /api/negocio/<id>/recomendaciones?dias=N",
            "POST /api/negocio/<id>/chat",
            "POST /api/negocio/<id>/operacion",
        ],
        "motor": estado_motor(),
    })


@app.get("/api/negocios")
def listar_negocios():
    try:
        filas = db.query("SELECT id, nombre, COALESCE(actividad_principal, '') AS actividad, CONCAT_WS(', ', municipio, departamento) AS ubicacion FROM negocio ORDER BY id")
    except Exception as exc:
        return _bd_error(exc)
    return jsonify({"negocios": filas})


@app.get("/api/negocio/<int:negocio_id>")
def info_negocio(negocio_id):
    try:
        fila = db.query_one(
            "SELECT id, nombre, COALESCE(actividad_principal, '') AS actividad, CONCAT_WS(', ', municipio, departamento) AS ubicacion FROM negocio WHERE id = %s",
            (negocio_id,),
        )
    except Exception as exc:
        return _bd_error(exc)
    if not fila:
        return _no_encontrado()
    return jsonify(fila)


# ---------------------------------------------------------------------------
# Dashboard / Motor analítico
# ---------------------------------------------------------------------------

@app.get("/api/negocio/<int:negocio_id>/dashboard")
def dashboard(negocio_id):
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify(indicadores_principales(negocio_id))
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/ventas-por-dia")
def ventas_diarias(negocio_id):
    dias = request.args.get("dias", default=30, type=int)
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify({"ventas_por_dia": ventas_por_dia(negocio_id, dias)})
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/gastos-por-dia")
def gastos_diarios(negocio_id):
    dias = request.args.get("dias", default=30, type=int)
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify({"gastos_por_dia": gastos_por_dia(negocio_id, dias)})
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/top-productos")
def productos_top(negocio_id):
    n = request.args.get("n", default=5, type=int)
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify({"top_productos": top_productos(negocio_id, n)})
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/inventario-bajo")
def inventario_bajo_ep(negocio_id):
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify({"inventario_bajo": inventario_bajo(negocio_id)})
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/tendencia")
def tendencia_ep(negocio_id):
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify(tendencia_ventas(negocio_id))
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/perfil")
def perfil_ep(negocio_id):
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify(perfil_productivo(negocio_id))
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/proyeccion")
def proyeccion_ep(negocio_id):
    dias = request.args.get("dias", default=7, type=int)
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify(proyeccion_ventas_futuras(negocio_id, dias))
    except Exception as exc:
        return _bd_error(exc)


# ---------------------------------------------------------------------------
# Centro de Inteligencia (ML: predicción, inventario, anomalías, recomendación)
# ---------------------------------------------------------------------------

@app.get("/api/negocio/<int:negocio_id>/prediccion")
def prediccion_ep(negocio_id):
    """Predicción de ventas del negocio para los próximos `dias` días."""
    dias = request.args.get("dias", default=7, type=int)
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify(pronostico_negocio(negocio_id, dias))
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/inventario-predictivo")
def inventario_predictivo_ep(negocio_id):
    """Análisis de riesgo de inventario por producto (demanda estimada)."""
    dias = request.args.get("dias", default=7, type=int)
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify(analisis_inventario(negocio_id, dias))
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/anomalias")
def anomalias_ep(negocio_id):
    """Detección de comportamientos fuera del patrón habitual."""
    dias = request.args.get("dias", default=60, type=int)
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        return jsonify(detectar_anomalias(negocio_id, dias))
    except Exception as exc:
        return _bd_error(exc)


@app.get("/api/negocio/<int:negocio_id>/recomendaciones")
def recomendaciones_ep(negocio_id):
    """Recomendaciones accionables del negocio (se persisten en insight_ia)."""
    dias = request.args.get("dias", default=7, type=int)
    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        resultado = generar_recomendaciones(negocio_id, dias)
        guardadas = 0
        try:
            guardadas = registrar_recomendaciones(negocio_id, resultado, dias)
        except Exception:
            guardadas = 0
        payload = dict(resultado)
        payload["guardadas_en_insight"] = guardadas
        return jsonify(payload)
    except Exception as exc:
        return _bd_error(exc)


# ---------------------------------------------------------------------------
# Chat IA (interpretación) y confirmación de operaciones
# ---------------------------------------------------------------------------

def _resumen_operacion(op):
    """Genera una línea conversacional que resume una operación detectada
    (sección 19). La estructura técnica queda interna.

    Formato deseado (sección 19):
        "¡Listo! Registré la venta de 120 piñas a José por Q12 cada una.
         Total: Q1,440."
    """
    t = op.get("operacion") or {}
    tipo = op.get("tipo")

    try:
        cantidad = int(t.get("cantidad") or 0)
    except (TypeError, ValueError):
        cantidad = 0
    try:
        precio = float(t.get("precio_unitario") or 0)
    except (TypeError, ValueError):
        precio = 0.0

    producto = t.get("producto") or ""
    total = round(cantidad * precio, 2)

    if tipo == "venta":
        linea = f"Venta de {cantidad} {producto}"
        if t.get("cliente"):
            linea += f" a {t.get('cliente')}"
        if t.get("unidad"):
            linea += f" ({t.get('unidad')})"
        if precio:
            linea += f" por {_fmt_q(precio)} cada una"
        if total:
            linea += f". Total: {_fmt_q(total)}"
        return linea
    if tipo == "compra":
        linea = f"Compra de {cantidad} {producto}"
        if t.get("proveedor"):
            linea += f" a {t.get('proveedor')}"
        if t.get("unidad"):
            linea += f" ({t.get('unidad')})"
        if precio:
            linea += f" por {_fmt_q(precio)} cada una"
        if total:
            linea += f". Total: {_fmt_q(total)}"
        return linea
    if tipo == "gasto":
        return f"Gasto de {_fmt_q(t.get('monto'))} en {t.get('concepto') or 'concepto'}"
    if tipo == "inventario":
        return f"Inventario de {t.get('producto')} ({t.get('existencia')} unidades)"
    if tipo == "produccion":
        return f"Producción de {t.get('cantidad')} unidades de {t.get('producto')}"
    return op.get("tipo", "")


@app.post("/api/negocio/<int:negocio_id>/chat")
def chat(negocio_id):
    """Recibe lenguaje natural y devuelve la estructura detectada + token.

    NO guarda nada todavía: el frontend muestra [Confirmar][Corregir] y, al
    confirmar, llama a POST /operacion con el token.
    """
    cuerpo = request.get_json(silent=True) or {}
    mensaje = (cuerpo.get("mensaje") or "").strip()

    if not mensaje:
        return jsonify({"interpretado": False,
                        "mensaje": "Escribe una operación, por ejemplo: "
                                   "'Vendí 8 almuerzos a Q25'."}), 400

    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
    except Exception as exc:
        return _bd_error(exc)

    resultados = interpreter.interpretar_multiples(mensaje)

    # Consulta del usuario: el asesor responde con datos reales del negocio.
    if resultados and resultados[0].get("consulta"):
        return jsonify(_respuesta_consulta(negocio_id, resultados[0])), 200

    # Filtramos solo las operaciones interpretadas correctamente.
    validos = [r for r in resultados if r.get("interpretado")]

    if not validos:
        # Respaldo amigable: si fue una operación incompleta se muestran los
        # datos faltantes; si fue una pregunta desconocida, se ofrece ayuda.
        primero = resultados[0]
        if primero.get("errores"):
            lista = "\n".join("• " + e for e in primero["errores"])
            mensaje = (f"Faltan datos para completar la operación:\n{lista}\n\n"
                       "Escríbela completa, por ejemplo: 'Vendí 8 almuerzos a Q25'.")
        else:
            mensaje = ("Aún no entiendo esa pregunta, pero puedo ayudarte:\n"
                       "• Registrar: 'Vendí 8 almuerzos a Q25', 'Gasté Q150 comprando "
                       "verduras', 'Me quedan 10 gaseosas'.\n"
                       "• Consultar: '¿Qué productos tengo?', '¿Cómo van mis ventas?', "
                       "'Dame un resumen'.\n"
                       "Escribe 'ayuda' para ver todas las opciones.")
        return jsonify({"interpretado": False, "consulta": False, "tipo": "fallback",
                        "mensaje": mensaje}), 200

    # Crear una sesión de confirmación por cada operación detectada.
    operaciones = []
    for r in validos:
        token = service.nueva_sesion(r["operacion"])
        operaciones.append({
            "token_sesion": token,
            "tipo": r["tipo"],
            "operacion": r["operacion"],
            "mensaje_humano": r.get("mensaje_humano", mensaje),
            "errores": r.get("errores", []),
            "resumen": _resumen_operacion(r),
        })

    # Respuesta con forma completa (lista) y compatibilidad con la forma
    # simple previa apuntando a la primera operación.
    primer = operaciones[0]
    return jsonify({
        "interpretado": True,
        "multiples": len(operaciones) > 1,
        "operaciones": operaciones,
        "mensaje": "Detecté la información. ¿Confirmas que es correcta?",
        # Compatibilidad: forma simple para clientes existentes.
        "tipo": primer["tipo"],
        "operacion": primer["operacion"],
        "token_sesion": primer["token_sesion"],
        "mensaje_humano": primer["mensaje_humano"],
        "errores": primer["errores"],
        "resumen": primer["resumen"],
    })


@app.post("/api/negocio/<int:negocio_id>/operacion")
def confirmar_operacion(negocio_id):
    """Guarda una operación previamente interpretada y confirmada por el usuario."""
    cuerpo = request.get_json(silent=True) or {}
    token = cuerpo.get("token_sesion")
    mensaje = cuerpo.get("mensaje_humano")

    if not token:
        return jsonify({"error": "token_faltante", "mensaje": "Falta el token_sesion."}), 400

    try:
        if not negocio_existe(negocio_id):
            return _no_encontrado()
        resultado = service.guardar_operacion_confirmada(negocio_id, token, mensaje)
    except ValueError as ve:
        return jsonify({"error": "operacion_invalida", "mensaje": str(ve)}), 422
    except Exception as exc:
        return _bd_error(exc)

    # Devolver también los indicadores actualizados para que el dashboard reaccione.
    try:
        indicadores = indicadores_principales(negocio_id)
    except Exception:
        indicadores = None

    return jsonify({
        "guardado": True,
        "resultado": resultado,
        "indicadores": indicadores,
    })


if __name__ == "__main__":
    # En el host (Render/Railway) la variable PORT la inyecta la plataforma.
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() in ("1", "true"),
    )
