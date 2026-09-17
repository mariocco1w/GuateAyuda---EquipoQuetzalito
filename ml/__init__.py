"""Módulo de Machine Learning de GuateAyuda.

Expone la API pública de las capacidades de inteligencia:

    features         Preparación / feature engineering de datos (FASE 1)
    forecasting      Predicción de ventas e inventario (FASES 2-3)
    anomaly          Detección de anomalías (FASE 4)
    recommendations  Motor de recomendaciones (FASE 5)

El paquete NO inventa datos: todas las salidas se derivan de datos reales
almacenados en la base de datos via `db`. Cuando falta historial, devuelve
estado "no disponible" en lugar de fabricar resultados.
"""

from ml.features import (
    preparar_ventas_por_producto,
    preparar_series_diarias,
    resumen_features_negocio,
    serie_diaria_producto,
)
from ml.forecasting import (
    pronostico_demanda_negocio,
    pronostico_demanda_producto,
    pronostico_negocio,
    pronostico_producto,
    registrar_prediccion,
    ultima_prediccion,
)
from ml.inventory import (
    analisis_inventario,
    productos_por_agotarse,
)
from ml.anomaly import (
    anomalias_flagrantes,
    detectar_anomalias,
)
from ml.recommendations import (
    generar_recomendaciones,
    registrar_recomendaciones,
    resumen_recomendaciones,
)

__all__ = [
    "preparar_ventas_por_producto",
    "preparar_series_diarias",
    "resumen_features_negocio",
    "serie_diaria_producto",
    "pronostico_negocio",
    "pronostico_producto",
    "pronostico_demanda_negocio",
    "pronostico_demanda_producto",
    "registrar_prediccion",
    "ultima_prediccion",
    "analisis_inventario",
    "productos_por_agotarse",
    "detectar_anomalias",
    "anomalias_flagrantes",
    "generar_recomendaciones",
    "registrar_recomendaciones",
    "resumen_recomendaciones",
]
