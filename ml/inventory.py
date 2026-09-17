"""Análisis de inventario (FASE 3).

Conecta la predicción de demanda (unidades) con el inventario actual para
estimar por producto:

    consumo_esperado        Unidades que se espera consumir en el periodo.
    consumo_diario          Consumo promedio diario esperado.
    dias_hasta_agotamiento  Estimación de días restantes de existencia.
    riesgo                  ALTO / MEDIO / BAJO según horizonte.
    reposicion_sugerida     Cantidad recomendada a reponer (solo sugerencia).

Reglas del proyecto que se respetan:
    * NO se realizan compras automáticamente (solo sugerencia).
    * No inventar datos: si falta historial se dice `sin_datos`.
    * Reutiliza `ml.forecasting` y `ml.features` (no duplica lógica).
"""

from datetime import date

from ml.features import preparar_ventas_por_producto
from ml.forecasting import pronostico_demanda_producto

# Umbrales de riesgo (en días para el horizonte de predicción).
FACTOR_MEDIO = 2.0        # riesgo MEDIO si agotamiento <= dias * 2
MARGEN_SEGURIDAD = 1.2    # reposición cubre consumo esperado + 20%


def _riesgo(existencia, minimo, dias_hasta_agotamiento, dias):
    """Clasifica el riesgo de desabastecimiento de un producto."""
    if dias_hasta_agotamiento is None:
        return "BAJO"
    if existencia <= minimo:
        return "ALTO"
    if dias_hasta_agotamiento <= dias:
        return "ALTO"
    if dias_hasta_agotamiento <= dias * FACTOR_MEDIO:
        return "MEDIO"
    return "BAJO"


def analisis_inventario(negocio_id, dias=7):
    """Análisis de riesgo de inventario por producto para el negocio."""
    productos = preparar_ventas_por_producto(negocio_id)
    hoy = date.today()

    resultados = []
    for prod in productos:
        pid = prod["producto_id"]
        nombre = prod["producto"]
        existencia = prod["existencia"]
        minimo = prod["minimo"]

        demanda = pronostico_demanda_producto(
            negocio_id, pid, nombre, dias=dias)
        disponible = demanda.get("disponible", False)
        estado = demanda.get("estado", "sin_datos")

        if not disponible and estado == "sin_datos":
            # Sin historial: si ya está por debajo del mínimo, alertar igual.
            bajo_minimo = existencia <= minimo
            resultados.append({
                "producto_id": pid,
                "producto": nombre,
                "existencia": existencia,
                "minimo": minimo,
                "consumo_esperado": None,
                "consumo_diario": None,
                "dias_hasta_agotamiento": None,
                "riesgo": "ALTO" if bajo_minimo else "BAJO",
                "reposicion_sugerida": (
                    round(minimo - existencia, 2) if bajo_minimo else None),
                "estado_prediccion": "sin_datos",
                "mensaje": "Sin historial de ventas para estimar consumo.",
            })
            continue

        consumo_esperado = float(demanda.get("unidades") or 0.0) if disponible \
            else float(demanda.get("base_diaria") or 0.0) * dias
        consumo_diario = consumo_esperado / dias if dias > 0 else 0.0

        if consumo_diario > 0:
            dias_hasta = round(existencia / consumo_diario, 1)
        else:
            dias_hasta = None

        reposicion = 0.0
        if consumo_esperado and consumo_esperado > 0:
            objetivo = consumo_esperado * MARGEN_SEGURIDAD
            reposicion = round(max(0.0, objetivo - existencia), 2)

        nivel = _riesgo(existencia, minimo, dias_hasta, dias)

        resultados.append({
            "producto_id": pid,
            "producto": nombre,
            "existencia": existencia,
            "minimo": minimo,
            "consumo_esperado": round(consumo_esperado, 2),
            "consumo_diario": round(consumo_diario, 2),
            "dias_hasta_agotamiento": dias_hasta,
            "riesgo": nivel,
            "reposicion_sugerida": reposicion,
            "estado_prediccion": estado,
            "mensaje": demanda.get("mensaje", ""),
        })

    return {
        "disponible": len(resultados) > 0,
        "negocio_id": negocio_id,
        "periodo_dias": dias,
        "fecha_generacion": hoy.isoformat(),
        "productos": resultados,
        "en_riesgo": [r for r in resultados if r["riesgo"] == "ALTO"],
        "sin_datos": [r for r in resultados
                      if r["estado_prediccion"] == "sin_datos"],
        "mensaje": ("Estimación de inventario basada en demanda histórica. "
                    "No se realizan compras automáticamente."),
    }


def productos_por_agotarse(negocio_id, dias=7, riesgo_minimo="MEDIO"):
    """Lista de productos con riesgo de agotamiento (para alertas)."""
    analisis = analisis_inventario(negocio_id, dias=dias)
    niveles = {"BAJO": 0, "MEDIO": 1, "ALTO": 2}
    umbral = niveles.get(riesgo_minimo, 1)
    return [
        {
            "producto": r["producto"],
            "existencia": r["existencia"],
            "consumo_diario": r["consumo_diario"],
            "dias_hasta_agotamiento": r["dias_hasta_agotamiento"],
            "riesgo": r["riesgo"],
            "reposicion_sugerida": r["reposicion_sugerida"],
        }
        for r in analisis["productos"]
        if niveles.get(r["riesgo"], 0) >= umbral
    ]