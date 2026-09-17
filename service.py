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
import re
import unicodedata

import db

# Estado de operaciones pendientes de confirmación (en memoria).
# token_sesion -> estructura detectada por el intérprete.
OPERACIONES_PENDIENTES = {}


def _normalizar_nombre(texto):
    """Normaliza un nombre para búsqueda única (minúsculas, sin tildes).

    Sección 16: 'Piñas' y 'piñas' deben considerarse equivalentes para buscar
    productos existentes sin eliminar productos realmente distintos
    (p.ej. 'piña' vs 'piña golden').
    """
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.lower().split())


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


def _buscar_o_crear_producto(negocio_id, nombre, precio=None, crear_sin_precio=False):
    """Busca un producto por nombre (normalizado); si no existe lo crea.

    `crear_sin_precio=True` permite alta en inventario/producción sin precio
    de referencia. Si `precio` es None y no se permite crear sin precio,
    no se crea el producto (evita altas ambiguas en compras).
    """
    if not nombre:
        return None

    nombre = (nombre or "").strip(" .,").strip()
    if not nombre:
        return None

    nombre_norm = _normalizar_nombre(nombre)

    # Todos los productos del negocio, comparar normalizado en Python para
    # manejar tildes (la BD puede no ser normalizable en SQL de forma portable).
    filas = db.query(
        "SELECT id, nombre FROM producto WHERE negocio_id = %s",
        (negocio_id,),
    )
    for fila in filas:
        if _normalizar_nombre(fila.get("nombre")) == nombre_norm:
            return fila.get("id")

    # Búsqueda rápida por nombre exacto (case-insensitive) como respaldo.
    fila = db.query_one(
        "SELECT id FROM producto WHERE negocio_id = %s AND LOWER(nombre) = LOWER(%s)",
        (negocio_id, nombre),
    )
    if fila:
        return fila["id"]

    # No crear productos con nombres que parecen frases o contienen números
    # (sección 17: validación antes de crear productos).
    if _es_nombre_sospechoso(nombre_norm):
        return None
    if precio is None and not crear_sin_precio:
        return None

    precio_guardado = precio if precio is not None else 0
    pid = _siguiente_id("producto")
    db.execute(
        "INSERT INTO producto (id, negocio_id, nombre, precio_referencia, precio, existencia, inventario_minimo, minimo) "
        "VALUES (%s, %s, %s, %s, %s, 0, 0, 0)",
        (pid, negocio_id, nombre, precio_guardado, precio_guardado),
    )
    return pid


def _es_nombre_sospechoso(nombre):
    """True si un nombre de producto parece una oración, no un producto real.

    Validaciones de la sección 17:
    1. ¿El nombre contiene números?
    2. ¿Contiene precios?
    3. ¿Contiene símbolos monetarios?
    4. ¿Contiene una persona detectada como cliente?
    5. ¿Contiene un proveedor?
    6. ¿Contiene verbos de venta/compra?
    7. ¿Parece una oración completa?
    8. ¿Es demasiado largo para ser un nombre de producto?

    Importante: no marcar como moneda nombres de producto que solo *contienen*
    la raíz "quetzal" (p.ej. cerveza Quetzalteca / quetzaltecas).
    """
    if not nombre:
        return True
    # Contiene números
    if any(c.isdigit() for c in nombre):
        return True
    palabras = nombre.split()
    # Demasiado largo
    if len(palabras) > 4:
        return True
    # Contiene símbolo monetario (palabra completa, no subcadena de marca)
    if re.search(r"[qQ]\s*\d|\bgtq\b|\bquetzales?\b", nombre, re.IGNORECASE):
        return True
    # Es demasiado largo en caracteres (más de 35)
    if len(nombre) > 35:
        return True
    # Solo contiene palabras de contexto (no hay sustantivo real)
    contexto = {"a", "al", "la", "el", "los", "le", "les", "para", "con",
                "por", "de", "del", "en", "un", "una", "se", "me", "mi",
                "hoy", "dia", "tambien", "cantidad", "total", "mejor"}
    palabras_set = set()
    for p in palabras:
        base = unicodedata.normalize("NFD", p.lower())
        base = "".join(c for c in base if unicodedata.category(c) != "Mn")
        palabras_set.add(base)
    if palabras_set and palabras_set.issubset(contexto):
        return True
    return False


def _siguiente_id(tabla):
    fila = db.query_one(f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {tabla}")
    return int(fila["max_id"]) + 1


def _registrar_interaccion(negocio_id, mensaje_humano, estructura, confirmado):
    try:
        iid = _siguiente_id("interaccion")
        tipo = (estructura.get("tipo") or "").upper()
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            "INSERT INTO interaccion "
            "(id, negocio_id, mensaje_original, intent, tipo_detectado, estructura, datos_extraidos, confirmado, creado_en) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                iid, negocio_id, mensaje_humano, tipo,
                estructura.get("tipo"), to_json(estructura), to_json(estructura),
                1 if confirmado else 0, ahora,
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
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO transaccion (id, negocio_id, tipo, fecha, descripcion, monto) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, "VENTA", ahora, f"Venta de {cantidad} {nombre}", subtotal),
    )
    db.execute(
        "INSERT INTO detalle_venta "
        "(id, negocio_id, transaccion_id, producto_id, cantidad, precio_unitario, subtotal) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, tid, producto_id, cantidad, precio_unitario, subtotal),
    )

    # Actualizar inventario (descontar lo vendido).
    _descontar_inventario(negocio_id, nombre, cantidad)

    return {"tipo": "venta", "producto": nombre, "cantidad": cantidad,
            "precio_unitario": precio_unitario, "total": subtotal}


def guardar_compra(negocio_id, operacion):
    """Guarda una compra (PURCHASE). Suma inventario y asocia proveedor."""
    nombre = (operacion.get("producto") or "").strip()
    cantidad = int(operacion.get("cantidad") or 0)
    precio_unitario = float(operacion.get("precio_unitario") or 0)
    proveedor = (operacion.get("proveedor") or "").strip() or None

    if not nombre or cantidad <= 0:
        raise ValueError("Datos de compra incompletos o inválidos.")

    subtotal = round(cantidad * precio_unitario, 2)  # cálculo en Python

    precio_ref = precio_unitario if precio_unitario > 0 else None
    producto_id = _buscar_o_crear_producto(negocio_id, nombre, precio_ref)
    if producto_id is None:
        raise ValueError(f"No se pudo asociar el producto '{nombre}'.")

    tid = _siguiente_id("transaccion")
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proveedor_txt = f" a {proveedor}" if proveedor else ""
    db.execute(
        "INSERT INTO transaccion (id, negocio_id, tipo, fecha, descripcion, monto, atributos) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, "COMPRA", ahora,
         f"Compra de {cantidad} {nombre}{proveedor_txt}", subtotal,
         to_json({"proveedor": proveedor})),
    )
    db.execute(
        "INSERT INTO detalle_venta "
        "(id, negocio_id, transaccion_id, producto_id, cantidad, precio_unitario, subtotal) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, tid, producto_id, cantidad, precio_unitario, subtotal),
    )

    # Actualizar inventario (sumar lo comprado).
    fila = db.query_one(
        "SELECT COALESCE(existencia, 0) AS existencia FROM producto WHERE id = %s",
        (producto_id,),
    )
    base = float(fila["existencia"])
    nueva = base + cantidad
    db.execute(
        "UPDATE producto SET existencia = %s WHERE id = %s",
        (nueva, producto_id),
    )
    _registrar_movimiento(negocio_id, producto_id, "ENTRADA", cantidad,
                          f"Compra de {cantidad} {nombre}")

    return {"tipo": "compra", "producto": nombre, "cantidad": cantidad,
            "precio_unitario": precio_unitario, "proveedor": proveedor,
            "total": subtotal}


def guardar_gasto(negocio_id, operacion):
    """Guarda un gasto."""
    monto = float(operacion.get("monto") or 0)
    concepto = (operacion.get("concepto") or operacion.get("descripcion") or "Gasto").strip()

    if monto <= 0:
        raise ValueError("Monto de gasto inválido o ausente.")

    tid = _siguiente_id("transaccion")
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO transaccion (id, negocio_id, tipo, fecha, descripcion, monto) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, "GASTO", ahora, concepto, monto),
    )
    return {"tipo": "gasto", "concepto": concepto, "monto": monto}


def guardar_inventario(negocio_id, operacion):
    """Actualiza/crea el inventario de un producto."""
    nombre = (operacion.get("producto") or "").strip()
    existencia = int(operacion.get("existencia") or 0)

    if not nombre or existencia < 0:
        raise ValueError("Datos de inventario inválidos.")

    producto_id = _buscar_o_crear_producto(
        negocio_id, nombre, precio=0, crear_sin_precio=True
    )
    if producto_id is None:
        raise ValueError(f"No se pudo asociar el producto '{nombre}'.")

    # Si es un ingreso (ENTRADA), se suma a la existencia actual en lugar de
    # reemplazarla; si no, se establece la existencia declarada.
    if operacion.get("movimiento") == "ENTRADA":
        fila = db.query_one(
            "SELECT COALESCE(existencia, 0) AS existencia FROM producto WHERE id = %s",
            (producto_id,),
        )
        base = float(fila["existencia"])
        nueva = base + existencia
        db.execute(
            "UPDATE producto SET existencia = %s WHERE id = %s",
            (nueva, producto_id),
        )
        _registrar_movimiento(negocio_id, producto_id, "ENTRADA", existencia,
                              f"Ingreso de {existencia} {nombre}")
        return {"tipo": "inventario", "producto": nombre, "existencia": nueva,
                "movimiento": "ENTRADA"}

    db.execute(
        "UPDATE producto SET existencia = %s WHERE id = %s",
        (existencia, producto_id),
    )
    _registrar_movimiento(negocio_id, producto_id, "AJUSTE", existencia,
                          f"Existencia declarada de {existencia} {nombre}")
    return {"tipo": "inventario", "producto": nombre, "existencia": existencia}


def guardar_produccion(negocio_id, operacion):
    """Registra producción: incrementa la existencia del producto fabricado."""
    nombre = (operacion.get("producto") or "").strip()
    cantidad = int(operacion.get("cantidad") or 0)

    if not nombre or cantidad <= 0:
        raise ValueError("Datos de producción incompletos o inválidos.")

    producto_id = _buscar_o_crear_producto(
        negocio_id, nombre, precio=0, crear_sin_precio=True
    )
    if producto_id is None:
        raise ValueError(f"No se pudo asociar el producto '{nombre}'.")

    fila = db.query_one(
        "SELECT COALESCE(existencia, 0) AS existencia FROM producto WHERE id = %s",
        (producto_id,),
    )
    base = float(fila["existencia"])
    nueva = base + cantidad
    db.execute(
        "UPDATE producto SET existencia = %s WHERE id = %s",
        (nueva, producto_id),
    )
    _registrar_movimiento(negocio_id, producto_id, "PRODUCCION", cantidad,
                          f"Producción de {cantidad} {nombre}")
    return {"tipo": "produccion", "producto": nombre, "cantidad": cantidad,
            "existencia": nueva}


def _registrar_movimiento(negocio_id, producto_id, tipo, cantidad, descripcion):
    """Registra un movimiento de inventario (ENTRADA/PRODUCCION/AJUSTE)."""
    try:
        mid = _siguiente_id("movimiento_inventario")
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            "INSERT INTO movimiento_inventario "
            "(id, negocio_id, producto_id, tipo, cantidad_delta, descripcion, creado_en) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (mid, negocio_id, producto_id, tipo, cantidad, descripcion, ahora),
        )
    except Exception as exc:
        print(f"[warn] No se pudo registrar el movimiento de inventario: {exc}")


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
    elif tipo == "compra":
        resultado = guardar_compra(negocio_id, estructura)
    elif tipo == "gasto":
        resultado = guardar_gasto(negocio_id, estructura)
    elif tipo == "inventario":
        resultado = guardar_inventario(negocio_id, estructura)
    elif tipo == "produccion":
        resultado = guardar_produccion(negocio_id, estructura)
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
