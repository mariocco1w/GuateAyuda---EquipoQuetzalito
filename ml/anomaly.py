"""Detección de anomalías (FASE 4).

Detecta comportamientos fuera del patrón habitual en ventas, gastos,
compras, inventario y producción usando un método estadístico robusto
(mediana + desviación absoluta mediana / z-score MAD).

Reglas del proyecto que se respetan:
    * NO se asume fraude ni error: cada resultado se presenta como
      "requiere revisión".
    * No inventar datos; si no hay historia suficiente se dice `sin_datos`.
    * No presentar alarmas como certezas: siempre se acompaña de contexto.
    * Reutiliza `db.py` como única fuente de datos.
"""

from datetime import datetime, timedelta
from statistics import median

import db

# Umbral z-score MAD: valores más allá de 3 MAD se consideran inusuales.
Z_THRESHOLD = 3.0
# Mínimo de observaciones para poder detectar un patrón.
MIN_OBSERVACIONES = 5

_SQL_VENTAS_DIARIAS = "GROUP BY t.fecha::date"
_SQL_GASTOS_DIARIOS = "UPPER(tipo) = 'GASTO'"
_SQL_COMPRAS_DIARIAS = "UPPER(tipo) = 'COMPRA'"
_SQL_MOVIMIENTOS = "FROM movimiento_inventario"


def _fecha_corte(dias):
    """Fecha ISO de corte para filtrar los últimos `dias`."""
    return (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")


def _percentil(ordenada, p):
    """Percentil simple de una lista ORDENADA ascendente (0-100)."""
    if not ordenada:
        return 0.0
    n = len(ordenada)
    pos = (n - 1) * (p / 100.0)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return ordenada[lo] + (ordenada[hi] - ordenada[lo]) * frac


def _mad_zscore(valores):
    """z-score MAD de una serie (mediana + desviación absoluta mediana).

    Devuelve 0 para todos si no hay dispersión (robusto a atípicos).
    Se conserva con fines de diagnóstico; la detección principal usa
    `_indices_atipicos` (IQR + regla relativa a la mediana).
    """
    n = len(valores)
    if n < MIN_OBSERVACIONES:
        return [0.0] * n
    med = median(valores)
    diffs = [abs(v - med) for v in valores]
    mad = median(diffs)
    if mad == 0:
        return [0.0] * n
    k = 0.6745
    return [round((v - med) / (k * mad), 2) for v in valores]


def _indices_atipicos(valores):
    """Índices de valores considerados fuera del patrón habitual.

    Combina dos reglas estadísticas:
      1. IQR: fuera de [Q1 - 1.5*IQR, Q3 + 1.5*IQR].
      2. Serie plana (IQR=0): desviación relativa a la mediana >= 50%.

    Devuelve dict {indice: score} donde `score` mide qué tan atípico es.
    """
    n = len(valores)
    if n < MIN_OBSERVACIONES:
        return {}

    ordenada = sorted(valores)
    q1 = _percentil(ordenada, 25)
    q3 = _percentil(ordenada, 75)
    iqr = q3 - q1

    indices = {}
    if iqr > 0:
        lim_inf = q1 - 1.5 * iqr
        lim_sup = q3 + 1.5 * iqr
        for i, v in enumerate(valores):
            if lim_inf <= v <= lim_sup:
                continue
            if v > lim_sup:
                score = (v - q3) / iqr
            else:
                score = (q1 - v) / iqr
            indices[i] = round(abs(score), 2)
    else:
        # Serie sin variabilidad entre cuartiles: usar la mediana como base.
        med = median(valores)
        if med != 0:
            for i, v in enumerate(valores):
                desv = abs(v - med) / abs(med)
                if desv >= 0.5:
                    indices[i] = round(desv, 2)
        else:
            for i, v in enumerate(valores):
                if v != 0:
                    indices[i] = 1.0
    return indices


def _anomalias_de_serie(etiqueta, series, z_umbral=Z_THRESHOLD):
    """Detecta anomalías en una serie de valores.

    `series`: lista de (fecha, valor, contexto). Devuelve lista de dicts:
        fecha, valor, mediana, zscore, direccion, requiere_revision, mensaje
    """
    vals = [float(r["valor"]) for r in series]
    atipicos = _indices_atipicos(vals)
    med = median(vals) if vals else 0.0

    anomalias = []
    for idx, score in atipicos.items():
        fila = series[idx]
        valor = float(fila["valor"])
        direccion = "alta" if valor > med else "baja"
        porcentaje = 0.0
        if med != 0:
            porcentaje = round(abs((valor - med) / med) * 100, 1)

        anomalias.append({
            "etiqueta": etiqueta,
            "fecha": fila.get("fecha"),
            "valor": valor,
            "mediana": round(med, 2),
            "zscore": score,
            "direccion": direccion,
            "desviacion_porcentual": porcentaje,
            "contexto": fila.get("contexto"),
            "requiere_revision": True,
            "mensaje": (f"{etiqueta.capitalize()} de {fila.get('fecha')} "
                        f"fue {porcentaje:.1f}% {'más' if direccion == 'alta' else 'menos'} "
                        f"que lo habitual ({round(med, 2)}). Requiere revisión."),
        })
    return anomalias


def _serie_diaria(sql, negocio_id, dias=60):
    """Serie diaria (fecha, valor) desde una consulta SQL."""
    filas = db.query(sql, (negocio_id, _fecha_corte(dias)))
    if dias and dias > 0:
        filas = filas[-dias:]
    return [
        {
            "fecha": str(f["dia"]),
            "valor": float(f["total"] or 0),
            "contexto": None,
        }
        for f in filas
    ]


def _ventas_diarias(negocio_id, dias=60):
    """Ventas totales por día."""
    return _serie_diaria(
        """
        SELECT t.fecha::date AS dia, COALESCE(SUM(dv.subtotal), 0) AS total
        FROM transaccion t
        JOIN detalle_venta dv ON dv.transaccion_id = t.id
        WHERE t.negocio_id = %s AND UPPER(t.tipo) = 'VENTA'
          AND t.fecha >= %s
        GROUP BY t.fecha::date
        ORDER BY t.fecha::date
        """,
        negocio_id, dias,
    )


def _gastos_diarios(negocio_id, dias=60):
    """Gastos totales por día (monto de transacciones tipo GASTO)."""
    return _serie_diaria(
        """
        SELECT fecha::date AS dia, COALESCE(SUM(monto), 0) AS total
        FROM transaccion
        WHERE negocio_id = %s AND UPPER(tipo) = 'GASTO'
          AND fecha >= %s
        GROUP BY fecha::date
        ORDER BY fecha::date
        """,
        negocio_id, dias,
    )


def _compras_diarias(negocio_id, dias=60):
    """Compras totales por día."""
    return _serie_diaria(
        """
        SELECT fecha::date AS dia, COALESCE(SUM(monto), 0) AS total
        FROM transaccion
        WHERE negocio_id = %s AND UPPER(tipo) = 'COMPRA'
          AND fecha >= %s
        GROUP BY fecha::date
        ORDER BY fecha::date
        """,
        negocio_id, dias,
    )


def _movimientos_inventario(negocio_id, dias=60):
    """Movimientos de inventario (salidas/entradas) por producto y día.

    Detecta consumo/producción inusual por producto, no por tipo exacto
    (para no duplicar alertas de ventas).
    """
    filas = db.query(
        """
        SELECT p.nombre AS producto,
               mi.creado_en::date AS dia,
               SUM(CASE WHEN mi.cantidad_delta < 0
                        THEN ABS(mi.cantidad_delta) ELSE 0 END) AS salida,
               SUM(CASE WHEN mi.cantidad_delta > 0
                        THEN mi.cantidad_delta ELSE 0 END) AS entrada
        FROM movimiento_inventario mi
        JOIN producto p ON p.id = mi.producto_id
        WHERE mi.negocio_id = %s
          AND mi.creado_en >= %s
        GROUP BY p.nombre, mi.creado_en::date
        ORDER BY mi.creado_en::date
        """,
        (negocio_id, _fecha_corte(dias)),
    )
    if dias and dias > 0:
        filas = filas[-dias:]
    return [
        {
            "fecha": str(f["dia"]),
            "valor": float(f["salida"] or 0),
            "contexto": f"Movimientos de inventario de {f['producto']}",
        }
        for f in filas
    ]


def detectar_anomalias(negocio_id, dias=60):
    """Detecta anomalías en ventas, gastos, compras e inventario.

    Devuelve la lista de hallazgos agrupada por tipo. Si no hay datos
    suficientes para una categoría, se reporta sin datos.
    """
    areas = {
        "ventas": _ventas_diarias(negocio_id, dias),
        "gastos": _gastos_diarios(negocio_id, dias),
        "compras": _compras_diarias(negocio_id, dias),
        "inventario": _movimientos_inventario(negocio_id, dias),
    }

    resultado = {}
    total_anomalias = 0
    for area, serie in areas.items():
        if not serie:
            resultado[area] = {
                "disponible": False,
                "mensaje": ("Sin historial suficiente de "
                            f"{area} para detectar patrones."),
                "anomalias": [],
            }
            continue
        valores = [float(r["valor"]) for r in serie]
        if len(valores) < MIN_OBSERVACIONES:
            resultado[area] = {
                "disponible": False,
                "mensaje": (f"No hay suficientes días de {area} para detectar "
                            "patrones (mínimo 5)."),
                "anomalias": [],
            }
            continue
        anomalias = _anomalias_de_serie(area, serie)
        resultado[area] = {
            "disponible": True,
            "dias_revisados": len(valores),
            "anomalias": anomalias,
        }
        total_anomalias += len(anomalias)

    return {
        "disponible": total_anomalias > 0,
        "negocio_id": negocio_id,
        "periodo_dias": dias,
        "areas": resultado,
        "total_anomalias": total_anomalias,
        "mensaje": (
            "Anomalías detectadas como datos fuera del patrón habitual. "
            "No se concluye fraude ni error: requieren revisión humana."
            if total_anomalias else
            "Sin comportamientos inusuales en el periodo revisado."
        ),
    }


def anomalias_flagrantes(negocio_id, dias=60):
    """Devuelve directamente la lista de hallazgos que requieren revisión."""
    deteccion = detectar_anomalias(negocio_id, dias)
    todas = []
    for area, bloque in deteccion.get("areas", {}).items():
        for a in bloque.get("anomalias", []):
            a["area"] = area
            todas.append(a)
    return todas