"""Motor de recomendaciones (FASE 5).

Combina las salidas de predicción, anomalías, tendencias, inventario y
finanzas para generar recomendaciones comprensibles y accionables.

Cada recomendación tiene la estructura:

    tipo          Categoría (inventario / ventas / gastos / anomalia / finanzas)
    prioridad     ALTA / MEDIA / BAJA
    titulo        Título legible
    explicacion   Contexto con datos que la sustentan
    accion_sugerida  Qué puede hacer el usuario
    origen        Origen del dato (prediccion / inventario / anomalia /
                  tendencia / finanzas)

Reglas del proyecto que se respetan:
    * Toda recomendación se basa en datos reales (no se inventa).
    * No se presenta ninguna recomendación como certeza.
    * No se llama "ganancia" a ventas - gastos.
    * No se duplica lógica: reutiliza ml.features / ml.forecasting /
      ml.inventory / ml.anomaly.
"""

from datetime import date, timedelta

import db
from analytics.engine import indicadores_principales, tendencia_ventas
from ml.anomaly import anomalias_flagrantes
from ml.forecasting import pronostico_negocio
from ml.inventory import analisis_inventario

TIPO_INSIGHT = "RECOMENDACION"
LIMITE_RECOMENDACIONES = 12


def _reco(tipo, prioridad, titulo, explicacion, accion, origen):
    """Construye un dict de recomendación con su forma canónica."""
    return {
        "tipo": tipo,
        "prioridad": prioridad,
        "titulo": titulo,
        "explicacion": explicacion,
        "accion_sugerida": accion,
        "origen": origen,
    }


def _recomendaciones_inventario(inventario, dias):
    """Recomendaciones derivadas del análisis de inventario."""
    recomendaciones = []
    for prod in inventario.get("productos", []):
        riesgo = prod["riesgo"]
        if riesgo != "ALTO":
            continue
        detalle = (f"existencias actuales de {prod['existencia']:.0f} unidades "
                   f"(mínimo {prod['minimo']:.0f})")
        accion = f"Revisa el inventario de {prod['producto']}."
        if prod["consumo_diario"]:
            detalle += (f", consumo estimado de {prod['consumo_diario']:.1f}/día "
                        f"→ {prod['dias_hasta_agotamiento']} días restantes")
        if prod.get("reposicion_sugerida"):
            accion += (f" Considera reponer con {prod['reposicion_sugerida']:.0f} "
                       "unidades (solo sugerencia, decide tú).")
        recomendaciones.append(_reco(
            "inventario",
            "ALTA",
            f"Riesgo de quedarte sin {prod['producto']}",
            f"Con {detalle}, el inventario podría no ser suficiente. "
            "Esto es una estimación, no una certeza.",
            accion,
            "inventario",
        ))
    return recomendaciones


def _recomendaciones_tendencia(negocio_id):
    """Recomendaciones basadas en la tendencia de ventas."""
    tend = tendencia_ventas(negocio_id)
    if not tend.get("disponible"):
        return []
    cambio = tend.get("cambio_porcentual")
    if cambio is None:
        return []
    if cambio <= -10.0:
        return [_reco(
            "ventas", "MEDIA",
            "Las ventas están disminuyendo",
            f"El promedio de ventas bajó {abs(cambio):.1f}% respecto al "
            "periodo anterior.",
            "Revisa qué días o productos bajaron más y considera una "
            "promoción o ajuste.",
            "tendencia",
        )]
    if cambio >= 10.0:
        return [_reco(
            "ventas", "MEDIA",
            "Las ventas están aumentando",
            f"El promedio de ventas subió {cambio:.1f}% respecto al periodo "
            "anterior.",
            "Prepárate para mayor demanda: revisa inventario y producción.",
            "tendencia",
        )]
    return []


def _recomendaciones_prediccion(negocio_id, dias):
    """Recomendaciones basadas en la proyección de ventas."""
    proy = pronostico_negocio(negocio_id, dias=dias)
    if not proy.get("disponible"):
        return []
    total_periodo = round(sum(p["estimado"] for p in proy["predicciones"]), 0)
    mensaje_estado = ("el modelo prevé" if proy["estado"] == "modelo_ml"
                      else "la estimación histórica prevé")
    return [_reco(
        "ventas", "BAJA",
        "Demanda esperada para los próximos días",
        f"Se esperan ventas de alrededor de Q{total_periodo:,.0f} en los "
        f"próximos {dias} días ({mensaje_estado}). Es una estimación, no una "
        "certeza.",
        "Usa esta estimación para planificar compras y producción.",
        "prediccion",
    )]


def _recomendaciones_anomalias(negocio_id):
    """Recomendaciones derivadas de anomalías detectadas."""
    anomalias = anomalias_flagrantes(negocio_id)
    recomendaciones = []
    for a in anomalias[:5]:
        recomendaciones.append(_reco(
            "anomalia",
            "ALTA" if a.get("direccion") == "alta" else "MEDIA",
            f"Comportamiento inusual en {a.get('area', a.get('etiqueta'))}",
            a.get("mensaje", "Se detectó un dato fuera del patrón habitual."),
            "Revisa el día señalado para confirmar si la información es "
            "correcta.",
            "anomalia",
        ))
    return recomendaciones


def _recomendaciones_finanzas(negocio_id):
    """Recomendaciones financieras básicas (sin llamar "ganancia")."""
    ind = indicadores_principales(negocio_id)
    ventas = ind["ventas_registradas"]
    gastos = ind["gastos_registrados"]
    if ventas <= 0 or gastos <= 0:
        return []
    proporcion = (gastos / ventas) * 100.0
    if proporcion >= 80.0:
        return [_reco(
            "finanzas", "MEDIA",
            "Los gastos representan una parte alta de las ventas",
            f"Los gastos registrados (Q{gastos:,.0f}) equivalen al "
            f"{proporcion:.0f}% de las ventas (Q{ventas:,.0f}).",
            "Revisa tus gastos y busca oportunidades de reducción.",
            "finanzas",
        )]
    return []


def generar_recomendaciones(negocio_id, dias=7):
    """Genera todas las recomendaciones del negocio.

    Combina inventario, tendencia, predicción, anomalías y finanzas.
    Ordena por prioridad ALTA > MEDIA > BAJA y limita el resultado.
    """
    inventario = analisis_inventario(negocio_id, dias)
    reco = []
    reco += _recomendaciones_inventario(inventario, dias)
    reco += _recomendaciones_tendencia(negocio_id)
    reco += _recomendaciones_prediccion(negocio_id, dias)
    reco += _recomendaciones_anomalias(negocio_id)
    reco += _recomendaciones_finanzas(negocio_id)

    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    reco.sort(key=lambda r: (orden.get(r["prioridad"], 3), r["tipo"]))
    reco = [r for r in reco if r["prioridad"] in ("ALTA", "MEDIA")][
        :LIMITE_RECOMENDACIONES]

    return {
        "disponible": True,
        "negocio_id": negocio_id,
        "fecha_generacion": date.today().isoformat(),
        "periodo_dias": dias,
        "recomendaciones": reco,
        "total": len(reco),
        "mensaje": ("Recomendaciones generadas a partir de datos reales del "
                    "negocio (estimaciones, no certezas)."),
    }


def resumen_recomendaciones(negocio_id, dias=7):
    """Resumen ligero (titulos + prioridad) para el intérprete / chat."""
    resultado = generar_recomendaciones(negocio_id, dias)
    return [
        {
            "prioridad": r["prioridad"],
            "titulo": r["titulo"],
            "tipo": r["tipo"],
        }
        for r in resultado["recomendaciones"]
    ]


def registrar_recomendaciones(negocio_id, resultado=None, dias=7):
    """Persiste las recomendaciones en `insight_ia`.

    Reemplaza recomendaciones anteriores del negocio (tipo RECOMENDACION).
    Devuelve el número de recomendaciones guardadas.
    """
    import json

    if resultado is None:
        resultado = generar_recomendaciones(negocio_id, dias)

    recomendaciones = resultado.get("recomendaciones", [])
    if not recomendaciones:
        return 0

    db.execute(
        "DELETE FROM insight_ia WHERE negocio_id = %s AND tipo = %s",
        (negocio_id, TIPO_INSIGHT),
    )
    db.execute(
        "INSERT INTO insight_ia "
        "(negocio_id, tipo, titulo, descripcion, evidencia, confidence, "
        "modelo, version_modelo, estado, generado_en, expira_en) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            negocio_id,
            TIPO_INSIGHT,
            f"Recomendaciones para tu negocio ({len(recomendaciones)})",
            resultado.get("mensaje", ""),
            json.dumps({
                "recomendaciones": recomendaciones,
                "fecha_generacion": resultado.get("fecha_generacion"),
                "periodo_dias": dias,
            }, ensure_ascii=False),
            0.75,
            "RecommendationEngine",
            "1.0.0",
            "ACTIVO",
            date.today().isoformat(),
            (date.today() + timedelta(days=dias)).isoformat(),
        ),
    )
    return len(recomendaciones)