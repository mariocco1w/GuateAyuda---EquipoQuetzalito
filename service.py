"""Capa de servicio / persistencia de GuateAyuda.

Une el intérprete conversacional con la base de datos. Se encarga de:

    * Guardar una operación confirmada (venta, gasto, inventario).
    * Calcular los TOTALES en Python (nunca la IA ni el intérprete) - sección 12.
    * Registrar la interacción humano -> interpretación -> estructura -> confirmación
      (tabla `interaccion`, sección 14).
    * Manejar tokens de sesión para el flujo [Confirmar][Corregir] (sección 7).

Depende del esquema definido por el compañero de `bd` (sección 14):
    negocio, producto, transaccion, detalle_venta, interaccion.
"""

from datetime import datetime
from uuid import uuid4

import db

# Estado de operaciones pendientes de confirmación (en memoria).
# token_sesion -> estructura detectada por el intérprete.
OPERACIONES_PENDIENTES = {}


def nueva_sesion(estructura):
    """Crea un token de sesión asociado a una estructura para confirmar."""
    token = str(uuid4())
    OPERACIONES_PENDIENTES[token] = {
        "estructura": estructura,
        "creada": datetime.now(),
    }
    return token


def obtener_sesion(token):
    """Devuelve la estructura pendiente asociada al token, o None."""
    sesion = OPERACIONES_PENDIENTES.get(token)
    return sesion["estructura"] if sesion else None


def eliminar_sesion(token):
    OPERACIONES_PENDIENTES.pop(token, None)


def _buscar_o_crear_producto(negocio_id, nombre, precio=None):
    """Busca un producto por nombre; si no existe y hay precio, lo crea."""
    if not nombre:
        return None

    fila = db.query_one(
        "SELECT id FROM producto WHERE negocio_id = %s AND LOWER(nombre) = LOWER(%s)",
        (negocio_id, nombre),
    )
    if fila:
        return fila["id"]

    if precio is None:
        return None

    pid = _siguiente_id("producto")
    db.execute(
        "INSERT INTO producto (id, negocio_id, nombre, precio, existencia, minimo) "
        "VALUES (%s, %s, %s, %s, 0, 0)",
        (pid, negocio_id, nombre, precio),
    )
    return pid


def _siguiente_id(tabla):
    fila = db.query_one(f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {tabla}")
    return int(fila["max_id"]) + 1


def _registrar_interaccion(negocio_id, mensaje_humano, estructura, confirmado):
    try:
        iid = _siguiente_id("interaccion")
        db.execute(
            "INSERT INTO interaccion "
            "(id, negocio_id, mensaje_original, tipo_detectado, datos_extraidos, confirmado, fecha) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                iid, negocio_id, mensaje_humano, estructura.get("tipo"),
                to_json(estructura), confirmado, datetime.now(),
            ),
        )
    except Exception as exc:  # no romper el guardado principal por el registro
        print(f"[warn] No se pudo registrar la interacción: {exc}")


def to_json(obj):
    """Serialización simple a JSON string (evita dependencia extra)."""
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Guardar operaciones confirmadas
# ---------------------------------------------------------------------------

def guardar_venta(negocio_id, operacion):
    """Guarda una venta. Calcula el subtotal en PYTHON (sección 12)."""
    nombre = (operacion.get("producto") or "").strip()
    cantidad = int(operacion.get("cantidad") or 0)
    precio_unitario = float(operacion.get("precio_unitario") or 0)

    if not nombre or cantidad <= 0 or precio_unitario <= 0:
        raise ValueError("Datos de venta incompletos o inválidos.")

    subtotal = round(cantidad * precio_unitario, 2)  # cálculo en Python

    producto_id = _buscar_o_crear_producto(negocio_id, nombre, precio_unitario)

    if producto_id is None:
        raise ValueError(f"No se pudo asociar el producto '{nombre}'.")

    tid = _siguiente_id("transaccion")
    db.execute(
        "INSERT INTO transaccion (id, negocio_id, tipo, fecha, descripcion, monto) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, "venta", datetime.now(), f"Venta de {cantidad} {nombre}", subtotal),
    )
    db.execute(
        "INSERT INTO detalle_venta "
        "(id, transaccion_id, producto_id, cantidad, precio_unitario, subtotal) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (tid, tid, producto_id, cantidad, precio_unitario, subtotal),
    )

    # Actualizar inventario (descontar lo vendido).
    _descontar_inventario(negocio_id, nombre, cantidad)

    return {"tipo": "venta", "producto": nombre, "cantidad": cantidad,
            "precio_unitario": precio_unitario, "total": subtotal}


def guardar_gasto(negocio_id, operacion):
    """Guarda un gasto."""
    monto = float(operacion.get("monto") or 0)
    concepto = (operacion.get("concepto") or operacion.get("descripcion") or "Gasto").strip()

    if monto <= 0:
        raise ValueError("Monto de gasto inválido o ausente.")

    tid = _siguiente_id("transaccion")
    db.execute(
        "INSERT INTO transaccion (id, negocio_id, tipo, fecha, descripcion, monto) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, "gasto", datetime.now(), concepto, monto),
    )
    return {"tipo": "gasto", "concepto": concepto, "monto": monto}


def guardar_inventario(negocio_id, operacion):
    """Actualiza/crea el inventario de un producto."""
    nombre = (operacion.get("producto") or "").strip()
    existencia = int(operacion.get("existencia") or 0)

    if not nombre or existencia < 0:
        raise ValueError("Datos de inventario inválidos.")

    producto_id = _buscar_o_crear_producto(negocio_id, nombre, 0)
    if producto_id is None:
        raise ValueError(f"No se pudo asociar el producto '{nombre}'.")

    db.execute(
        "UPDATE producto SET existencia = %s WHERE id = %s",
        (existencia, producto_id),
    )
    return {"tipo": "inventario", "producto": nombre, "existencia": existencia}


def _descontar_inventario(negocio_id, nombre, cantidad):
    """Resta la cantidad vendida al inventario existente del producto."""
    try:
        db.execute(
            "UPDATE producto SET existencia = GREATEST(COALESCE(existencia,0) - %s, 0) "
            "WHERE negocio_id = %s AND LOWER(nombre) = LOWER(%s)",
            (cantidad, negocio_id, nombre),
        )
    except Exception as exc:
        print(f"[warn] No se pudo descontar inventario: {exc}")


def guardar_operacion_confirmada(negocio_id, token_sesion, mensaje_humano=None):
    """Guarda la estructura asociada a un token ya confirmado por el usuario.

    Suma la operación a la BD y registra la interacción con confirmado=True.
    """
    estructura = obtener_sesion(token_sesion)
    if estructura is None:
        raise ValueError("Sesión no válida o expirada. Vuelve a intentar la operación.")

    tipo = estructura.get("tipo")

    if tipo == "venta":
        resultado = guardar_venta(negocio_id, estructura)
    elif tipo == "gasto":
        resultado = guardar_gasto(negocio_id, estructura)
    elif tipo == "inventario":
        resultado = guardar_inventario(negocio_id, estructura)
    else:
        raise ValueError("Tipo de operación no soportado.")

    _registrar_interaccion(
        negocio_id,
        mensaje_humano or "",
        estructura,
        confirmado=True,
    )
    eliminar_sesion(token_sesion)
    return resultado
