"""Motor analítico de GuateAyuda.

Expone la API pública del motor para el resto de la aplicación.
"""

from analytics.engine import (
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

__all__ = [
    "indicadores_principales",
    "ventas_por_dia",
    "gastos_por_dia",
    "top_productos",
    "inventario_bajo",
    "productos_de_negocio",
    "tendencia_ventas",
    "perfil_productivo",
    "proyeccion_ventas_futuras",
    "proyeccion_ml",
    "estado_motor",
]
