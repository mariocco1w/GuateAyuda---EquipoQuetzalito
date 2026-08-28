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
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


import db
from analytics import (
    estado_motor,
    gastos_por_dia,
    indicadores_principales,
    inventario_bajo,
    perfil_productivo,
    proyeccion_ml,
    proyeccion_ventas_futuras,
    tendencia_ventas,
    top_productos,
    ventas_por_dia,
)
import interpreter
import service

app = Flask(__name__)
app.secret_key = "supersecretkey"  # En producción, usar variable de entorno


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
        # Simulación simple de registro
        session["user_id"] = 1
        session["negocio_id"] = 1
        return redirect(url_for("configuracion_empresa"))
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/empresa/configuracion", methods=["GET", "POST"])
@login_required
def configuracion_empresa():
    return render_template("configuracion.html")


@app.get("/dashboard")
@login_required
def dashboard_view():
    return render_template("dashboard.html")


@app.get("/chat")
@login_required
def chat_view():
    return render_template("chat.html")



@app.get("/reportes")
@login_required
def generar_reporte():
    negocio_id = session.get("negocio_id")
    
    # Crear PDF en memoria
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.drawString(100, 750, f"Reporte de Negocio: {negocio_id}")
    p.drawString(100, 730, "Resumen: Ventas, Gastos, Producción.")
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="reporte.pdf", mimetype="application/pdf")




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
            "POST /api/negocio/<id>/chat",
            "POST /api/negocio/<id>/operacion",
        ],
        "motor": estado_motor(),
    })


@app.get("/api/negocios")
def listar_negocios():
    try:
        filas = db.query("SELECT id, nombre, COALESCE(actividad_principal, actividad) AS actividad, COALESCE(ubicacion, municipio, departamento) AS ubicacion FROM negocio ORDER BY id")
    except Exception as exc:
        return _bd_error(exc)
    return jsonify({"negocios": filas})


@app.get("/api/negocio/<int:negocio_id>")
def info_negocio(negocio_id):
    try:
        fila = db.query_one(
            "SELECT id, nombre, COALESCE(actividad_principal, actividad) AS actividad, COALESCE(ubicacion, municipio, departamento) AS ubicacion FROM negocio WHERE id = %s",
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
# Chat IA (interpretación) y confirmación de operaciones
# ---------------------------------------------------------------------------

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

    resultado = interpreter.interpretar(mensaje)

    if not resultado.get("interpretado"):
        return jsonify(resultado), 422

    # Crear la sesión pendiente de confirmación.
    token = service.nueva_sesion(resultado["operacion"])

    return jsonify({
        "interpretado": True,
        "token_sesion": token,
        "tipo": resultado["tipo"],
        "operacion": resultado["operacion"],
        "mensaje_humano": mensaje,
        "errores": resultado.get("errores", []),
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
    app.run(debug=True, port=5000)
