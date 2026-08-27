"""Motor analítico de GuateAyuda.

Estructura en capas (inspirada en ai-business-command-center):

    Capa A  Análisis descriptivo  -> reglas + datos (central del MVP)
    Capa B  Forecasting simple    -> media móvil / tendencia (datos + reglas, NO ML)
    Capa C  Puerto ML futuro      -> desactivado en el MVP (ver contexto, sección 13)

Reglas del proyecto que se respetan aquí:
    * No ML predictivo en el MVP (sección 13).
    * No llamar "ganancia" a ventas menos gastos (sección 9).
    * Los cálculos los hace Python/reglas, no la IA (sección 12).
    * No inventar métricas; si faltan datos se reporta (sección 23).
"""

from datetime import timedelta

import db

# Tipo de operaciones reconocidos por el MVP (sección 8).
TIPO_VENTA = "venta"
TIPO_GASTO = "gasto"


# ---------------------------------------------------------------------------
# Capa A: Análisis descriptivo (reglas + datos)
# ---------------------------------------------------------------------------

def indicadores_principales(negocio_id):
    """Indicadores principales del dashboard (sección 9):
    ventas registradas, gastos registrados, número de operaciones, productos activos.
    """
    total_ventas = db.query_one(
        "SELECT COALESCE(SUM(dv.subtotal), 0) AS total "
        "FROM detalle_venta dv "
        "JOIN transaccion t ON t.id = dv.transaccion_id "
        "WHERE t.negocio_id = %s",
        (negocio_id,),
    )["total"]

    total_gastos = db.query_one(
        "SELECT COALESCE(SUM(monto), 0) AS total "
        "FROM transaccion "
        "WHERE negocio_id = %s AND tipo = %s",
        (negocio_id, TIPO_GASTO),
    )["total"]

    num_operaciones = db.query_one(
        "SELECT COUNT(*) AS n FROM transaccion WHERE negocio_id = %s",
        (negocio_id,),
    )["n"]

    productos_activos = db.query_one(
        "SELECT COUNT(*) AS n FROM producto WHERE negocio_id = %s",
        (negocio_id,),
    )["n"]

    return {
        "ventas_registradas": float(total_ventas or 0),
        "gastos_registrados": float(total_gastos or 0),
        "numero_operaciones": int(num_operaciones or 0),
        "productos_activos": int(productos_activos or 0),
    }


def ventas_por_dia(negocio_id, dias=30):
    """Serie temporal de ventas (fecha + total) para gráficas (Chart.js)."""
    filas = db.query(
        """
        SELECT t.fecha::date AS dia, COALESCE(SUM(dv.subtotal), 0) AS total
        FROM transaccion t
        JOIN detalle_venta dv ON dv.transaccion_id = t.id
        WHERE t.negocio_id = %s AND t.tipo = %s
        GROUP BY t.fecha::date
        ORDER BY t.fecha::date DESC
        LIMIT %s
        """,
        (negocio_id, TIPO_VENTA, dias),
    )
    filas.reverse()
    return [{"dia": str(f["dia"]), "total": float(f["total"])} for f in filas]


def gastos_por_dia(negocio_id, dias=30):
    """Serie temporal de gastos (fecha + monto)."""
    filas = db.query(
        """
        SELECT fecha::date AS dia, COALESCE(SUM(monto), 0) AS total
        FROM transaccion
        WHERE negocio_id = %s AND tipo = %s
        GROUP BY fecha::date
        ORDER BY fecha::date DESC
        LIMIT %s
        """,
        (negocio_id, TIPO_GASTO, dias),
    )
    filas.reverse()
    return [{"dia": str(f["dia"]), "total": float(f["total"])} for f in filas]


def top_productos(negocio_id, n=5):
    """Productos de mayor movimiento, ordenados por ingresos generados."""
    filas = db.query(
        """
        SELECT p.nombre,
               SUM(dv.cantidad) AS unidades,
               SUM(dv.subtotal) AS ingresos
        FROM detalle_venta dv
        JOIN transaccion t ON t.id = dv.transaccion_id
        JOIN producto p ON p.id = dv.producto_id
        WHERE t.negocio_id = %s AND t.tipo = %s
        GROUP BY p.nombre
        ORDER BY ingresos DESC
        LIMIT %s
        """,
        (negocio_id, TIPO_VENTA, n),
    )
    return [
        {
            "producto": f["nombre"],
            "unidades": int(f["unidades"] or 0),
            "ingresos": float(f["ingresos"] or 0),
        }
        for f in filas
    ]


def inventario_bajo(negocio_id):
    """Productos con existencia <= mínimo (regla de la sección 13).

    Nota: requiere la columna `minimo` en la tabla `producto`. Si el esquema
    del compañero no la incluye aún, la consulta lo maneja con COALESCE.
    """
    filas = db.query(
        """
        SELECT nombre, existencia, COALESCE(minimo, 0) AS minimo
        FROM producto
        WHERE negocio_id = %s
          AND existencia <= COALESCE(minimo, 0)
        ORDER BY existencia ASC
        """,
        (negocio_id,),
    )
    return [
        {
            "producto": f["nombre"],
            "existencia": int(f["existencia"] or 0),
            "minimo": int(f["minimo"] or 0),
        }
        for f in filas
    ]


def tendencia_ventas(negocio_id, periodos=2):
    """Compara períodos consecutivos y describe el cambio porcentual.

    Usa media móvil simple sobre los últimos `periodos` bloques de 7 días.
    Se reporta como "registradas", nunca como predicción (sección 13 y 23).
    """
    filas = db.query(
        """
        SELECT fecha::date AS dia, COALESCE(SUM(dv.subtotal), 0) AS total
        FROM transaccion t
        JOIN detalle_venta dv ON dv.transaccion_id = t.id
        WHERE t.negocio_id = %s AND t.tipo = %s
        GROUP BY t.fecha::date
        ORDER BY t.fecha::date
        """,
        (negocio_id, TIPO_VENTA),
    )
    if len(filas) < 2:
        return {
            "disponible": False,
            "mensaje": "No hay suficiente historial para calcular una tendencia.",
        }

    totales = [float(f["total"]) for f in filas]
    periodo = 7
    bloques = []
    for i in range(0, len(totales), periodo):
        corte = totales[i : i + periodo]
        bloques.append(sum(corte) / len(corte))

    if len(bloques) < 2:
        return {
            "disponible": False,
            "mensaje": "No hay suficiente historial para calcular una tendencia.",
        }

    anterior = bloques[-2]
    actual = bloques[-1]
    if anterior == 0:
        cambio = None
    else:
        cambio = round(((actual - anterior) / anterior) * 100, 1)

    if cambio is None:
        texto = "No hay ventas previas registradas para comparar."
    elif cambio >= 0:
        texto = f"Las ventas registradas aumentaron {cambio:.1f}%."
    else:
        texto = f"Las ventas registradas disminuyeron {abs(cambio):.1f}%."

    return {"disponible": True, "cambio_porcentual": cambio, "mensaje": texto}


def perfil_productivo(negocio_id, negocio_nombre=None, actividad=None):
    """Datos del Perfil Productivo Digital (sección 10).

    IMPORTANTE: este perfil se construye con la actividad registrada por el
    negocio. NO se afirma verificación externa (sección 10 y 23).
    """
    if not negocio_nombre or not actividad:
        info = db.query_one(
            "SELECT nombre, actividad FROM negocio WHERE id = %s", (negocio_id,)
        )
        if info:
            negocio_nombre = negocio_nombre or info["nombre"]
            actividad = actividad or info["actividad"]

    indicadores = indicadores_principales(negocio_id)

    dias_actividad = db.query_one(
        "SELECT COUNT(DISTINCT fecha::date) AS n FROM transaccion WHERE negocio_id = %s",
        (negocio_id,),
    )["n"]

    productos = db.query_one(
        "SELECT COUNT(*) AS n FROM producto WHERE negocio_id = %s", (negocio_id,)
    )["n"]

    inventario_ok = db.query_one(
        "SELECT COALESCE(SUM(CASE WHEN existencia > 0 THEN 1 ELSE 0 END), 0) > 0 AS ok "
        "FROM producto WHERE negocio_id = %s",
        (negocio_id,),
    )["ok"]

    return {
        "negocio": negocio_nombre,
        "actividad": actividad,
        "productos_activos": int(productos or 0),
        "dias_con_actividad": int(dias_actividad or 0),
        "operaciones": int(indicadores["numero_operaciones"]),
        "informacion_disponible": {
            "ventas": indicadores["ventas_registradas"] > 0,
            "gastos": indicadores["gastos_registrados"] > 0,
            "productos": int(productos or 0) > 0,
            "inventario": bool(inventario_ok),
            "produccion": False,  # el MVP no registra producción todavía
        },
        "verificado_externamente": False,
    }


# ---------------------------------------------------------------------------
# Capa B: Forecasting simple (media móvil / tendencia, NO modelos ML)
# ---------------------------------------------------------------------------

def proyeccion_ventas_futuras(negocio_id, dias=7):
    """Proyección de ventas por media móvil simple.

    Es una ESTIMACIÓN por reglas (datos + tendencia), NO una predicción con
    modelo. Se etiqueta como "proyección bajo hipótesis" (sección 23).

    Devuelve la base promedio diaria y la proyección de los próximos `dias`.
    """
    filas = db.query(
        """
        SELECT fecha::date AS dia, COALESCE(SUM(dv.subtotal), 0) AS total
        FROM transaccion t
        JOIN detalle_venta dv ON dv.transaccion_id = t.id
        WHERE t.negocio_id = %s AND t.tipo = %s
        GROUP BY t.fecha::date
        ORDER BY t.fecha::date
        """,
        (negocio_id, TIPO_VENTA),
    )

    if len(filas) < 3:
        return {
            "disponible": False,
            "mensaje": "No hay suficiente historial para proyectar (mínimo 3 días con ventas).",
            "etiqueta": "proyeccion_bajo_hipotesis",
        }

    ultimo_dia = max(f["dia"] for f in filas)
    if not hasattr(ultimo_dia, "date"):
        ultimo_dia = ultimo_dia

    dias_recientes = 14
    recientes = [float(f["total"]) for f in filas][-dias_recientes:]
    base_diaria = sum(recientes) / len(recientes)

    proyeccion = [
        {
            "dia": str(ultimo_dia + timedelta(days=i + 1)),
            "estimado": round(base_diaria, 2),
        }
        for i in range(dias)
    ]

    return {
        "disponible": True,
        "etiqueta": "proyeccion_bajo_hipotesis",
        "base_diaria": round(base_diaria, 2),
        "periodo_dias": dias,
        "proyeccion": proyeccion,
        "metodo": "media_movil_simple",
    }


# ---------------------------------------------------------------------------
# Capa C: Puerto ML futuro (desactivado en el MVP - sección 13 del contexto)
# ---------------------------------------------------------------------------

ML_HABILITADO = False


def proyeccion_ml(negocio_id, dias=7):
    """Respuesta de la capa ML. Desactivada en el MVP.

    Se deja la estructura lista para, en el futuro, entrenar con historial
    real (p. ej. la técnica del repo de fletes: feature engineering temporal +
    ensemble de gradient boosting, validación out-of-time). Hasta entonces,
    devuelve estado no disponible y NO presenta resultados como reales.
    """
    if not ML_HABILITADO:
        return {
            "disponible": False,
            "estado": "ml_desactivado",
            "razon": "MVP sin ML predictivo (falta historial real). "
            "Ver contexto, sección 13.",
        }

    # Punto de integración futuro: cargar modelo desde ml/ y predecir.
    raise NotImplementedError("Motor ML aún no entrenado para este MVP.")


def estado_motor():
    """Resumen del estado del motor para depuración / UI."""
    return {
        "capa_a_analitica": True,
        "capa_b_forecasting_simple": True,
        "capa_c_ml": ML_HABILITADO,
    }
