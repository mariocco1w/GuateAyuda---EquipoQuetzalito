"""Capa de preparación de datos para Machine Learning (FASE 1).

Construye `features` a partir de datos reales de la base de datos:

    ventas_diarias       Serie temporal de ventas diarias.
    ventas_por_producto  Ventas desglosadas por producto (para predicción)
    consumo_inventario   Consumo histórico por producto (desde movimientos)
    resumen_features     Indicadores consolidados por negocio / producto.

Reglas del proyecto que se respetan:
    * No inventar datos; si faltan, reportar "no disponible".
    * Cálculos en Python/pandas, no en la IA del intérprete.
    * Reutilizar `db.py` como única fuente de datos.
"""

from datetime import date, datetime, timedelta

import pandas as pd

import db

# Palabras clave usadas para filtrar consultas en tests con la cadena SQL.
_SQL_VENTAS_DIARIAS = "GROUP BY t.fecha::date"
_SQL_VENTAS_PRODUCTO = "GROUP BY producto_id, fecha::date"
_SQL_MOV_INVENTARIO = "FROM movimiento_inventario"

# Ventana por defecto para promedios móviles.
VENTANA_CORTA = 7
VENTANA_LARGA = 30


def _a_date(valor):
    """Normaliza un valor de fecha (str/datetime/date) a datetime.date."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor)
    try:
        return datetime.fromisoformat(texto).date()
    except ValueError:
        try:
            return datetime.strptime(texto, "%Y-%m-%d").date()
        except ValueError:
            return None


def _parse_fila_venta(fila):
    """Convierte una fila de venta en un dict normalizado con fecha `date`."""
    return {
        "producto_id": fila.get("producto_id"),
        "producto": fila.get("nombre") or fila.get("producto"),
        "dia": _a_date(fila.get("dia", fila.get("fecha"))),
        "total": float(fila.get("total") or 0),
        "cantidad": float(fila.get("cantidad") or fila.get("unidades") or 0),
    }


def _serie_ventas_diarias(negocio_id, dias=90):
    """Devuelve la serie temporal de ventas diarias agregada por día."""
    filas = db.query(
        """
        SELECT t.fecha::date AS dia, COALESCE(SUM(dv.subtotal), 0) AS total,
               COALESCE(SUM(dv.cantidad), 0) AS cantidad
        FROM transaccion t
        JOIN detalle_venta dv ON dv.transaccion_id = t.id
        WHERE t.negocio_id = %s AND UPPER(t.tipo) = 'VENTA'
        GROUP BY t.fecha::date
        ORDER BY t.fecha::date
        """,
        (negocio_id,),
    )
    if dias and dias > 0:
        filas = filas[-dias:]
    return [_parse_fila_venta(f) for f in filas]


def _serie_ventas_producto(negocio_id, dias=90):
    """Serie de ventas por producto (producto_id + fecha), útil para demanda."""
    filas = db.query(
        """
        SELECT p.id AS producto_id, p.nombre, t.fecha::date AS dia,
               SUM(dv.cantidad) AS cantidad, SUM(dv.subtotal) AS total
        FROM detalle_venta dv
        JOIN transaccion t ON t.id = dv.transaccion_id
        JOIN producto p ON p.id = dv.producto_id
        WHERE t.negocio_id = %s AND UPPER(t.tipo) = 'VENTA'
        GROUP BY producto_id, fecha::date
        ORDER BY t.fecha::date
        """,
        (negocio_id,),
    )
    if dias and dias > 0:
        filas = filas[-dias:]
    return [_parse_fila_venta(f) for f in filas]


def serie_diaria_producto(negocio_id, producto_id, dias=None):
    """Serie temporal diaria de ventas de UN producto (lista de dicts).

    Cada fila: {producto_id, producto, dia (date), cantidad, total}.
    Ordenada por fecha ascendente. Usada por la capa de predicción.
    """
    filas = _serie_ventas_producto(negocio_id, dias=dias)
    return [f for f in filas if f["producto_id"] == producto_id]


def _serie_movimientos_inventario(negocio_id, dias=90):
    """Movimientos de inventario históricos (consumo por producto).

    Devuelve por producto la suma de salidas y entradas, para estimar consumo.
    """
    filas = db.query(
        """
        SELECT producto_id, tipo,
               SUM(CASE WHEN cantidad_delta < 0 THEN -cantidad_delta ELSE 0 END) AS salidas,
               SUM(CASE WHEN cantidad_delta > 0 THEN cantidad_delta ELSE 0 END) AS entradas,
               COUNT(*) AS n_movimientos
        FROM movimiento_inventario
        WHERE negocio_id = %s
        GROUP BY producto_id, tipo
        """,
        (negocio_id,),
    )
    return [
        {
            "producto_id": f["producto_id"],
            "tipo": f["tipo"],
            "salidas": float(f["salidas"] or 0),
            "entradas": float(f["entradas"] or 0),
            "n_movimientos": int(f["n_movimientos"] or 0),
        }
        for f in filas
    ]


def _productos_con_inventario(negocio_id):
    """Productos del negocio con su inventario actual y mínimo."""
    filas = db.query(
        """
        SELECT id AS producto_id, nombre,
               COALESCE(existencia, 0) AS existencia,
               COALESCE(inventario_minimo, minimo, 0) AS minimo,
               COALESCE(precio_referencia, precio, 0) AS precio
        FROM producto
        WHERE negocio_id = %s AND activo = 1
        ORDER BY LOWER(nombre)
        """,
        (negocio_id,),
    )
    return [
        {
            "producto_id": f["producto_id"],
            "producto": f["nombre"],
            "existencia": float(f["existencia"] or 0),
            "minimo": float(f["minimo"] or 0),
            "precio": float(f["precio"] or 0),
        }
        for f in filas
    ]


def preparar_series_diarias(negocio_id, dias=90):
    """Serie temporal de ventas diarias totales con indicadores derivados.

    Devuelve un DataFrame (pandas) con una fila por día y las columnas:
        dia, total, promedio_7, promedio_30, tendencia, crecimiento.

    Si no hay datos suficientes, devuelve un DataFrame vacío (el llamador
    debe reportar "no disponible").
    """
    filas = _serie_ventas_diarias(negocio_id, dias=dias)
    if not filas:
        return pd.DataFrame()

    df = pd.DataFrame(filas)
    df["dia"] = pd.to_datetime(df["dia"])
    df = df.sort_values("dia").set_index("dia")

    # Rellenar los días sin ventas con 0 para que promedios móviles sean reales.
    fecha_min = df.index.min() - timedelta(days=VENTANA_LARGA)
    fecha_max = df.index.max()
    idx_completo = pd.date_range(fecha_min, fecha_max, freq="D")
    df = df.reindex(idx_completo, fill_value=0.0)

    df["promedio_7"] = df["total"].rolling(VENTANA_CORTA, min_periods=1).mean()
    df["promedio_30"] = df["total"].rolling(VENTANA_LARGA, min_periods=1).mean()

    # Tendencia: pendiente de regresión lineal simple sobre los últimos 7 días.
    df["tendencia"] = _tendencia_serie(df["total"])

    # Crecimiento: cambio porcentual entre promedios 7 y 30.
    df["crecimiento"] = df.apply(
        lambda r: _crecimiento(r["promedio_7"], r["promedio_30"]), axis=1
    )

    return df.reset_index()


def _tendencia_serie(serie, ventana=VENTANA_CORTA):
    """Pendiente normalizada de los últimos `ventana` valores ([-1, 1])."""
    valores = serie.astype(float).tail(ventana).tolist()
    valores = [0 if v is None or pd.isna(v) else v for v in valores]
    if len(valores) < 2 or max(valores) - min(valores) == 0:
        # Sin variación -> tendencia plana (misma longitud que la serie).
        return [0.0] * len(serie)
    # Regresión lineal simple: x = 0..n-1
    n = len(valores)
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(valores) / n
    numerador = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, valores))
    denominador = sum((xi - x_mean) ** 2 for xi in x)
    pendiente = numerador / denominador if denominador else 0.0
    # Normalizar pendiente por la magnitud de la serie.
    escala = max(valores) - min(valores) or 1.0
    pendiente_norm = (pendiente * n) / escala
    pendiente_norm = max(-1.0, min(1.0, pendiente_norm))
    return [pendiente_norm] * (len(serie) - len(valores)) + [pendiente_norm] * len(valores)


def _crecimiento(prom_7, prom_30):
    """Crecimiento porcentual entre promedios (None si no comparable)."""
    if prom_7 is None or prom_30 is None or pd.isna(prom_7) or pd.isna(prom_30):
        return None
    if prom_30 == 0:
        return None
    return round(((float(prom_7) - float(prom_30)) / float(prom_30)) * 100.0, 1)


def preparar_ventas_por_producto(negocio_id, dias=90):
    """Features de demanda por producto (para predicción e inventario).

    Devuelve una lista de dicts con:
        producto_id, producto,
        ventas_totales, dias_con_venta,
        promedio_diario_7, promedio_diario_30,
        tendencia, crecimiento, unidades_promedio,
        precio.
    """
    series = _serie_ventas_producto(negocio_id, dias=dias)
    productos = _productos_con_inventario(negocio_id)

    if not productos:
        return []

    df = pd.DataFrame(series)
    if df.empty:
        # Sin ventas en el periodo: devolver productos sin actividad.
        return [
            {
                **prod,
                "ventas_totales": 0.0,
                "dias_con_venta": 0,
                "promedio_diario_7": 0.0,
                "promedio_diario_30": 0.0,
                "tendencia": 0.0,
                "crecimiento": None,
                "unidades_promedio": 0.0,
            }
            for prod in productos
        ]
    df["dia"] = pd.to_datetime(df["dia"])

    resultado = []
    for prod in productos:
        pid = prod["producto_id"]
        sub = df[df["producto_id"] == pid]
        if sub.empty:
            resultado.append({
                **prod,
                "ventas_totales": 0.0,
                "dias_con_venta": 0,
                "promedio_diario_7": 0.0,
                "promedio_diario_30": 0.0,
                "tendencia": 0.0,
                "crecimiento": None,
                "unidades_promedio": 0.0,
            })
            continue

        sub = sub.set_index("dia").sort_index()
        fecha_max = sub.index.max()
        fecha_min = fecha_max - timedelta(days=VENTANA_LARGA)
        # Reindexar con la ventana para promedios solo sobre días con actividad.
        idx = pd.date_range(fecha_min, fecha_max, freq="D")
        sub = sub.reindex(idx)
        sub["total"] = sub["total"].fillna(0.0)
        sub["cantidad"] = sub["cantidad"].fillna(0.0)

        # Producir días indexados por fecha para ventana corta.
        df_7 = _filtrar_ventana(sub, dias=VENTANA_CORTA)

        prom_7 = float(df_7["total"].mean()) if not df_7.empty else 0.0
        prom_30 = float(sub["total"].mean()) if not sub.empty else 0.0
        unidades_7 = float(df_7["cantidad"].mean()) if not df_7.empty else 0.0

        tend = _tendencia_ultimo(sub["total"])
        crecimiento = _crecimiento(prom_7, prom_30)

        resultado.append({
            **prod,
            "ventas_totales": float(sub["total"].sum()),
            "dias_con_venta": int((sub["total"] > 0).sum()),
            "promedio_diario_7": round(prom_7, 2),
            "promedio_diario_30": round(prom_30, 2),
            "tendencia": round(tend, 3),
            "crecimiento": crecimiento,
            "unidades_promedio": round(unidades_7, 2),
        })
    return resultado


def _filtrar_ventana(df, dias):
    """Devuelve las últimas `dias` filas de un DataFrame indexado por fecha."""
    if df.empty:
        return df
    inicio = df.index.max() - timedelta(days=dias - 1)
    return df[df.index >= inicio]


def _tendencia_ultimo(df, ventana=VENTANA_CORTA):
    """Pendiente normalizada de la serie dada (un solo valor)."""
    serie = df.astype(float).tail(ventana)
    valores = [0 if pd.isna(v) else float(v) for v in serie.tolist()]
    if len(valores) < 2 or max(valores) - min(valores) == 0:
        return 0.0
    n = len(valores)
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(valores) / n
    num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, valores))
    den = sum((xi - x_mean) ** 2 for xi in x)
    pendiente = num / den if den else 0.0
    escala = max(valores) - min(valores) or 1.0
    return max(-1.0, min(1.0, (pendiente * n) / escala))


def resumen_features_negocio(negocio_id, dias=90):
    """Resumen consolidado de features por negocio (para la capa de ML).

    Devuelve:
        disponible        bool
        ventas_diarias    Series diarias (dict de listas)
        por_producto      Features de demanda por producto
        inventario        Inventario actual por producto
        consumo           Consumo histórico por producto
        mensaje           Mensaje cuando no hay datos suficientes
    """
    series = preparar_series_diarias(negocio_id, dias=dias)
    por_producto = preparar_ventas_por_producto(negocio_id, dias=dias)
    productos = _productos_con_inventario(negocio_id)
    movimientos = _serie_movimientos_inventario(negocio_id, dias=dias)

    if series.empty and not por_producto:
        return {
            "disponible": False,
            "mensaje": "No hay datos suficientes de ventas o productos "
            "para preparar features (FASE 1).",
            "ventas_diarias": [],
            "por_producto": [],
            "inventario": [],
            "consumo": [],
        }

    return {
        "disponible": True,
        "ventas_diarias": series.to_dict(orient="records"),
        "por_producto": por_producto,
        "inventario": productos,
        "consumo": movimientos,
    }
