"""Predicción de ventas (FASE 2).

Modelo de pronóstico para GuateAyuda:

    * Entrenamiento: si hay historial suficiente (>= MIN_DIAS_MODELO por
      producto), se entrena un modelo de regresión por producto usando como
      features: día de la semana (sin/cos) y tendencia temporal.
    * Fallback estadístico: si no hay suficientes datos, se usa el promedio
      diario (media móvil) y se marca como `fallback_estadistico` (el contexto
      exige avisarlo, no presentarlo como certeza).
    * Se registra cada predicción en la tabla `insight_ia` (tipo
      PREDICCION_VENTAS) con fecha, producto, modelo y métricas.

Reglas del proyecto que se respetan:
    * No presentar predicciones como certezas.
    * Si faltan datos, decirlo (fallback avisa explícitamente).
    * No duplicar lógica del motor analítico: se reutiliza `ml.features`.
"""

import json
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

import db
from ml.features import preparar_ventas_por_producto, serie_diaria_producto

# Umbrales de decisión.
MIN_DIAS_MODELO = 10      # Menos de esto -> fallback estadístico.
MIN_DIAS_HOLDOUT = 14     # Con esto ya se puede evaluar out-of-sample.
FRACCION_HOLDOUT = 0.25   # Última parte reservada para evaluar.

MODELO_NOMBRE = "LinearRegression"
MODELO_FALLBACK = "media_movil"
VERSION_MODELO = "1.0.0"
TIPO_INSIGHT = "PREDICCION_VENTAS"


# ---------------------------------------------------------------------------
# Construcción de features y predicción del modelo
# ---------------------------------------------------------------------------

def _features_fecha(fechas, origen):
    """Features temporales: día de la semana (sin/cos) + tendencia.

    `fechas` es un array de fechas (datetime) y `origen` la primera fecha
    (index 0). Devuelve una matriz (n, 3).
    """
    fechas_dt = pd.to_datetime(np.asarray(fechas, dtype="datetime64[ns]"))
    dow = np.array([f.weekday() for f in fechas_dt]).astype(float)
    sin_dow = np.sin((dow / 7.0) * 2 * np.pi).reshape(-1, 1)
    cos_dow = np.cos((dow / 7.0) * 2 * np.pi).reshape(-1, 1)
    dias_t = ((fechas_dt - pd.Timestamp(origen)).days
              .astype(float).values.reshape(-1, 1))
    return np.hstack([sin_dow, cos_dow, dias_t])


def _entrenar_modelo(series_producto, columna="total"):
    """Entrena y evalúa el modelo para un producto.

    `series_producto`: DataFrame con índice de fecha y columna objetivo
    (por defecto `total`). Devuelve (modelo, metricas, datos).
    """
    df = series_producto.copy()
    df = df.sort_index()
    df[columna] = df[columna].astype(float)

    n = len(df)
    usar_holdout = n >= MIN_DIAS_HOLDOUT
    n_test = int(n * FRACCION_HOLDOUT) if usar_holdout else 0
    train = df.iloc[: n - n_test] if n_test else df
    test = df.iloc[n - n_test:] if n_test else df.iloc[0:0]

    origen = train.index[0]
    X_train = _features_fecha(train.index, origen)
    y_train = train[columna].values

    model = LinearRegression()
    model.fit(X_train, y_train)

    y_train_pred = model.predict(X_train)
    metricas = {
        "rmse_entrenamiento": round(float(np.sqrt(
            mean_squared_error(y_train, y_train_pred))), 2),
        "mae_entrenamiento": round(float(mean_absolute_error(
            y_train, y_train_pred)), 2),
    }

    if not test.empty:
        X_test = _features_fecha(test.index, origen)
        y_test = test[columna].values
        y_test_pred = model.predict(X_test)
        metricas["rmse_holdout"] = round(float(np.sqrt(
            mean_squared_error(y_test, y_test_pred))), 2)
        metricas["mae_holdout"] = round(float(mean_absolute_error(
            y_test, y_test_pred)), 2)
        metricas["dias_holdout"] = len(test)
    else:
        metricas["warning"] = ("Sin holdout: la evaluación se hizo sobre "
                               "datos de entrenamiento.")

    return model, metricas, {
        "dias_entrenamiento": len(train),
        "dias_evaluados": len(test),
        "usar_holdout": usar_holdout,
    }


def _predecir_con_modelo(model, ultima_fecha, origen, dias):
    """Predice los próximos `dias` días a partir de `ultima_fecha`."""
    fechas_futuras = pd.date_range(
        ultima_fecha + timedelta(days=1), periods=dias, freq="D")
    X = _features_fecha(fechas_futuras, origen)
    estimados = np.maximum(model.predict(X), 0.0)
    return [
        {"dia": f.date().isoformat(), "estimado": round(float(v), 2)}
        for f, v in zip(fechas_futuras, estimados)
    ]


def _fallback_estadistico(series_producto, dias, mensaje_extra="",
                          columna="total"):
    """Promedio diario como predicción (etiquetado como fallback)."""
    df = series_producto.copy().sort_index()
    df[columna] = df[columna].astype(float)
    base = float(df[columna].mean()) if not df.empty else 0.0
    ultima_fecha = df.index.max()
    predicciones = []
    for i in range(dias):
        dia = (ultima_fecha + timedelta(days=i + 1)).date()
        predicciones.append({"dia": dia.isoformat(), "estimado": round(base, 2)})
    return {
        "estado": "fallback_estadistico",
        "modelo": MODELO_FALLBACK,
        "base_diaria": round(base, 2),
        "predicciones": predicciones,
        "metricas": {},
        "mensaje": ("Datos insuficientes para modelo ML; se usa promedio "
                    "diario como referencia." + mensaje_extra),
    }


def _preparar_serie_continua(negocio_id, producto_id):
    """Serie diaria continua del producto (días sin venta = 0).

    Mantiene `total` (ingresos) y `cantidad` (unidades) para poder predecir
    tanto ventas en dinero como demanda en unidades (inventario).
    """
    filas = serie_diaria_producto(negocio_id, producto_id)
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas)
    df["dia"] = pd.to_datetime(df["dia"])
    df = df.sort_values("dia").set_index("dia")
    df["total"] = df["total"].astype(float)
    df["cantidad"] = df["cantidad"].astype(float)
    idx = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(idx, fill_value=0.0)
    return df


# ---------------------------------------------------------------------------
# API pública: pronóstico por producto y por negocio
# ---------------------------------------------------------------------------

def pronostico_producto(negocio_id, producto_id, producto_nombre=None, dias=7):
    """Predicción de ventas de un producto para los próximos `dias` días."""
    df = _preparar_serie_continua(negocio_id, producto_id)
    hoy = date.today()

    if df.empty or len(df) < 2:
        return {
            "disponible": False,
            "estado": "sin_datos",
            "producto_id": producto_id,
            "producto": producto_nombre,
            "mensaje": "No hay historial de ventas para este producto aún.",
            "modelo": None,
            "predicciones": [],
            "metricas": {},
            "fecha_generacion": hoy.isoformat(),
        }

    if len(df) < MIN_DIAS_MODELO:
        return {
            **{
                "disponible": False,
                "producto_id": producto_id,
                "producto": producto_nombre,
                "fecha_generacion": hoy.isoformat(),
                "periodo_dias": dias,
            },
            **(_fallback_estadistico(
                df, dias,
                f" (se requieren al menos {MIN_DIAS_MODELO} días, se tienen "
                f"{len(df)}).")),
        }

    model, metricas, datos_entrenamiento = _entrenar_modelo(df)
    origen = df.index[0]
    ultima_fecha = df.index.max().date()
    predicciones = _predecir_con_modelo(model, ultima_fecha, origen, dias)

    return {
        "disponible": True,
        "estado": "modelo_ml",
        "producto_id": producto_id,
        "producto": producto_nombre,
        "modelo": MODELO_NOMBRE,
        "version_modelo": VERSION_MODELO,
        "fecha_generacion": hoy.isoformat(),
        "periodo_dias": dias,
        "predicciones": predicciones,
        "metricas": metricas,
        "entrenamiento": datos_entrenamiento,
        "dias_historico": len(df),
        "mensaje": "Predicción generada con modelo ML (estimación, no certeza).",
    }


def pronostico_negocio(negocio_id, dias=7):
    """Predicción de ventas del negocio completo (agrega por producto).

    Devuelve la suma diaria de los pronósticos individuales y el desglose
    por producto.
    """
    productos = preparar_ventas_por_producto(negocio_id)
    pronosticos = []
    total_por_dia = {}

    for prod in productos:
        pid = prod["producto_id"]
        res = pronostico_producto(negocio_id, pid, prod["producto"], dias=dias)
        if not res.get("disponible") and res.get("estado") == "sin_datos":
            continue
        pronosticos.append(res)
        for p in res.get("predicciones", []):
            dia = p["dia"]
            total_por_dia[dia] = total_por_dia.get(dia, 0.0) + p["estimado"]

    if not pronosticos:
        return {
            "disponible": False,
            "estado": "sin_datos",
            "negocio_id": negocio_id,
            "periodo_dias": dias,
            "predicciones": [],
            "por_producto": [],
            "mensaje": "No hay historial de ventas suficiente para pronosticar.",
        }

    predicciones = [
        {"dia": dia, "estimado": round(total, 2)}
        for dia, total in sorted(total_por_dia.items())
    ]

    usa_ml = any(p.get("estado") == "modelo_ml" for p in pronosticos)
    usa_fallback = any(p.get("estado") == "fallback_estadistico"
                       for p in pronosticos)

    if usa_ml and not usa_fallback:
        estado = "modelo_ml"
        mensaje = "Predicción generada con modelo ML (estimación, no certeza)."
    elif usa_ml and usa_fallback:
        estado = "mixto"
        mensaje = ("Predicción mixta: algunos productos usan modelo ML y otros "
                   "promedio histórico por falta de datos.")
    else:
        estado = "fallback_estadistico"
        mensaje = ("Datos insuficientes para modelo ML; se usa promedio "
                   "histórico como referencia.")

    return {
        "disponible": True,
        "estado": estado,
        "negocio_id": negocio_id,
        "modelo": MODELO_NOMBRE if usa_ml else MODELO_FALLBACK,
        "version_modelo": VERSION_MODELO,
        "fecha_generacion": date.today().isoformat(),
        "periodo_dias": dias,
        "predicciones": predicciones,
        "por_producto": [
            {
                "producto_id": p["producto_id"],
                "producto": p.get("producto"),
                "estado": p.get("estado"),
                "modelo": p.get("modelo"),
                "metricas": p.get("metricas", {}),
                "predicciones": p.get("predicciones", []),
            }
            for p in pronosticos
        ],
        "mensaje": mensaje,
    }


def pronostico_demanda_producto(negocio_id, producto_id, producto_nombre=None,
                                dias=7):
    """Predicción de DEMANDA en UNIDADES de un producto.

    Usa la serie de `cantidad` (unidades vendidas por día) con el mismo
    modelo que ventas. Base para el análisis de inventario (FASE 3).
    """
    df = _preparar_serie_continua(negocio_id, producto_id)
    hoy = date.today()

    if df.empty or len(df) < 2:
        return {
            "disponible": False,
            "estado": "sin_datos",
            "producto_id": producto_id,
            "producto": producto_nombre,
            "mensaje": "No hay historial de ventas para este producto aún.",
            "modelo": None,
            "predicciones": [],
            "metricas": {},
            "fecha_generacion": hoy.isoformat(),
            "unidades": 0.0,
        }

    if len(df) < MIN_DIAS_MODELO:
        fallback = _fallback_estadistico(df, dias, columna="cantidad")
        return {
            **{
                "disponible": False,
                "producto_id": producto_id,
                "producto": producto_nombre,
                "fecha_generacion": hoy.isoformat(),
                "periodo_dias": dias,
                "unidades": round(
                    fallback["base_diaria"] * dias, 2),
            },
            **fallback,
        }

    model, metricas, datos_entrenamiento = _entrenar_modelo(df, "cantidad")
    origen = df.index[0]
    ultima_fecha = df.index.max().date()
    predicciones = _predecir_con_modelo(model, ultima_fecha, origen, dias)
    unidades = round(sum(p["estimado"] for p in predicciones), 2)

    return {
        "disponible": True,
        "estado": "modelo_ml",
        "producto_id": producto_id,
        "producto": producto_nombre,
        "modelo": MODELO_NOMBRE,
        "version_modelo": VERSION_MODELO,
        "fecha_generacion": hoy.isoformat(),
        "periodo_dias": dias,
        "predicciones": predicciones,
        "metricas": metricas,
        "entrenamiento": datos_entrenamiento,
        "dias_historico": len(df),
        "unidades": unidades,
        "mensaje": "Predicción generada con modelo ML (estimación, no certeza).",
    }


def pronostico_demanda_negocio(negocio_id, dias=7):
    """Predicción de demanda en unidades por producto para el negocio.

    Devuelve lista con la demanda estimada (unidades) de cada producto.
    """
    productos = preparar_ventas_por_producto(negocio_id)
    resultados = []
    for prod in productos:
        res = pronostico_demanda_producto(
            negocio_id, prod["producto_id"], prod["producto"], dias=dias)
        if not res.get("disponible") and res.get("estado") == "sin_datos":
            continue
        resultados.append(res)
    return {
        "disponible": bool(resultados),
        "negocio_id": negocio_id,
        "periodo_dias": dias,
        "fecha_generacion": date.today().isoformat(),
        "por_producto": resultados,
        "mensaje": ("Predicción de demanda en unidades por producto "
                    "(estimación, no certeza).") if resultados else
            "No hay historial de ventas suficiente para pronosticar.",
    }


# ---------------------------------------------------------------------------
# Registro de predicciones (insight_ia)
# ---------------------------------------------------------------------------

def registrar_prediccion(negocio_id, resultado):
    """Guarda el último pronóstico en `insight_ia`.

    Reemplaza predicciones VENTAS anteriores del negocio (solo las de tipo
    PREDICCION_VENTAS) para no acumular duplicados.

    Devuelve True si se registró.
    """
    if not resultado.get("disponible"):
        return False

    predicciones = resultado.get("predicciones", [])
    if not predicciones:
        return False

    dias = resultado.get("periodo_dias", 0)
    expira = date.today() + timedelta(days=dias or 7)

    evidencia = {
        "predicciones": predicciones,
        "por_producto": [
            {
                "producto": p.get("producto"),
                "estado": p.get("estado"),
                "modelo": p.get("modelo"),
                "metricas": p.get("metricas", {}),
                "predicciones": p.get("predicciones", []),
            }
            for p in resultado.get("por_producto", [])
        ],
    }

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
            f"Predicción de ventas para los próximos {dias} días",
            resultado.get("mensaje", ""),
            json.dumps(evidencia, ensure_ascii=False),
            0.7 if resultado.get("estado") == "modelo_ml" else 0.4,
            resultado.get("modelo") or MODELO_FALLBACK,
            VERSION_MODELO,
            "ACTIVO",
            datetime.now().isoformat(),
            expira.isoformat(),
        ),
    )
    return True


def ultima_prediccion(negocio_id):
    """Devuelve la última predicción de ventas registrada (o None)."""
    filas = db.query(
        "SELECT * FROM insight_ia "
        "WHERE negocio_id = %s AND tipo = %s "
        "ORDER BY generado_en DESC LIMIT 1",
        (negocio_id, TIPO_INSIGHT),
    )
    if not filas:
        return None
    fila = filas[0]
    try:
        evidencia = json.loads(fila.get("evidencia") or "{}")
    except (TypeError, ValueError):
        evidencia = {}
    return {
        "titulo": fila.get("titulo"),
        "descripcion": fila.get("descripcion"),
        "evidencia": evidencia,
        "modelo": fila.get("modelo"),
        "confidence": float(fila.get("confidence") or 0),
        "generado_en": fila.get("generado_en"),
        "expira_en": fila.get("expira_en"),
    }