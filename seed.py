"""Genera datos demo para GuateAyuda.

Crea 8 negocios ficticios (sección 15 del contexto). El caso principal,
Comedor Doña María, se puebla en detalle para que el dashboard y el motor
analítico tengan qué calcular. Los datos son 100% ficticios y deben
identificarse como tal (marketing demo).

Compatibilidad: funciona sobre el esquema PostgreSQL de `bd/schema.sql`
(en Render) y sobre el fallback SQLite de `db.py`. Los ids son auto-generados
(GENERATED ALWAYS AS IDENTITY en PostgreSQL), por lo que NO se insertan ids
explícitos; se usa RETURNING para obtener el id generado.

Uso:
    python seed.py
    python seed.py --force   # re-crea el esquema y re-puebla desde cero
"""

import sqlite3
from datetime import date, timedelta

import db


# Marca clara de que son datos de demostración, no reales.
DEMO_TAG = "DEMO"


def _ejecutar_returning(sql, params):
    """Ejecuta un INSERT y devuelve la primer columna de la fila insertada."""
    conn = db.get_conn()
    try:
        if db._USE_SQLITE or isinstance(conn, sqlite3.Connection):
            sql_sqlite = db._convert_sql_for_sqlite(sql)
            # SQLite no soporta RETURNING; obtener el último id.
            cur = conn.cursor()
            cur.execute(sql_sqlite, params or ())
            conn.commit()
            cur.execute("SELECT last_insert_rowid()")
            return cur.fetchone()[0]
        else:
            with conn.cursor() as cur:
                cur.execute(sql + " RETURNING id", params)
                row = cur.fetchone()
                conn.commit()
                return row[0]
    except Exception:
        conn.rollback() if hasattr(conn, "rollback") else None
        raise
    finally:
        conn.close()


def _insertar_negocio(nombre, actividad, ubicacion):
    """Inserta un negocio y devuelve su id (auto-generado).

    El esquema de `negocio` usa `actividad_principal`, `departamento` y
    `municipio` (no hay columnas `actividad` ni `ubicacion`).
    """
    propietario = "María Xitumul" if "María" in nombre else "Propietario Demo"
    sql = (
        "INSERT INTO negocio "
        "(nombre, propietario, actividad_principal, descripcion, departamento, municipio) "
        "VALUES (%s, %s, %s, %s, %s, %s)"
    )
    return _ejecutar_returning(sql, (
        f"{nombre} ({DEMO_TAG})",
        propietario,
        actividad,
        "Negocio de demostración para GuateAyuda (no real).",
        "Guatemala",
        ubicacion,
    ))


def _insertar_producto(negocio_id, nombre, precio, existencia, minimo):
    """Inserta un producto y devuelve su id (auto-generado).

    El esquema de `producto` usa `precio_referencia` e `inventario_minimo`
    (no hay `precio` ni `minimo`).
    """
    sql = (
        "INSERT INTO producto "
        "(negocio_id, nombre, tipo_item, unidad_medida, precio_referencia, "
        "existencia, inventario_minimo, atributos) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    )
    return _ejecutar_returning(sql, (
        negocio_id,
        f"{nombre} ({DEMO_TAG})" ,
        "PRODUCTO",
        "unidad",
        precio,
        existencia,
        minimo,
        '{}',
    ))


def _insertar_venta(negocio_id, producto_id, cantidad, precio_unitario, fecha):
    """Inserta una transacción tipo venta + su detalle, devolviendo el total."""
    subtotal = cantidad * precio_unitario
    tid = _ejecutar_returning(
        "INSERT INTO transaccion "
        "(negocio_id, tipo, fecha, descripcion, monto, moneda, origen, estado) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (negocio_id, "VENTA", fecha, f"Venta (demo) de {cantidad} unidades",
         subtotal, "GTQ", "WEB", "CONFIRMADA"),
    )
    db.execute(
        "INSERT INTO detalle_venta "
        "(negocio_id, transaccion_id, producto_id, cantidad, precio_unitario, subtotal) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (negocio_id, tid, producto_id, cantidad, precio_unitario, subtotal),
    )
    return subtotal


def _insertar_gasto(negocio_id, descripcion, monto, fecha):
    """Inserta una transacción tipo gasto."""
    db.execute(
        "INSERT INTO transaccion "
        "(negocio_id, tipo, fecha, descripcion, monto, moneda, origen, estado) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (negocio_id, "GASTO", fecha, f"{descripcion} (demo)", monto,
         "GTQ", "WEB", "CONFIRMADA"),
    )


def seed_negocios_basicos():
    """Crea los 7 negocios complementarios con datos mínimos."""
    catalogos = [
        ("Café Chapín", "Venta de café y bebidas", "Zona 10, Ciudad de Guatemala",
         {"Café americano": (12, 40, 10), "Cappuccino": (20, 30, 8)}),
        ("Panadería Lupita", "Venta de pan y repostería", "Zona 3, Quetzaltenango",
         {"Pan francés": (2, 200, 50), "Champurradas": (1, 150, 60)}),
        ("Tienda El Quetzal", "Abarrotes y productos varios", "Zona 1, Huehuetenango",
         {"Gaseosa": (8, 100, 20), "Frijol (lb)": (12, 80, 25)}),
        ("Artesanías Maya", "Venta de artesanías y textiles", "Antigua Guatemala",
         {"Bolsos tejidos": (90, 12, 3), "Llaveros": (15, 60, 10)}),
        ("Frutas Don José", "Venta de frutas y verduras", "Mercado Central, Mazatenango",
         {"Banano (docena)": (10, 40, 10), "Tomate (lb)": (5, 30, 8)}),
        ("Textiles Ana", "Venta de cortes y telas", "Cobán, Alta Verapaz",
         {"Corte típico": (250, 8, 2), "Servilletas (docena)": (60, 20, 5)}),
        ("Dulces Chapines", "Venta de dulces típicos", "Zona 1, Chiquimula",
         {"Cocadas": (3, 100, 25), "Colochos de dulce": (5, 80, 20)}),
    ]

    for nombre, actividad, ubicacion, productos in catalogos:
        nid = _insertar_negocio(nombre, actividad, ubicacion)
        for pnombre, (precio, existencia, minimo) in productos.items():
            _insertar_producto(nid, pnombre, precio, existencia, minimo)
        print(f"  + {nombre}: {len(productos)} productos")


def seed_comedor_maria():
    """Puebla el caso principal (Comedor Doña María) con ~22 días de actividad."""
    nid = _insertar_negocio("Comedor Doña María", "Venta de alimentos", "Zona 5, Ciudad de Guatemala")

    # Precios y stock base reales por nombre.
    precios = {"Almuerzo": 25, "Café": 12, "Desayuno": 20, "Pan con pollo": 15, "Gaseosa": 10}
    stock_base = {"Almuerzo": 40, "Café": 80, "Desayuno": 25, "Pan con pollo": 50, "Gaseosa": 12}

    # Crear productos y registrar el mapa nombre -> id auto-generado.
    productos = {}
    for nombre, precio in precios.items():
        pid_ = _insertar_producto(nid, nombre, precio, stock_base[nombre], 10)
        productos[nombre] = pid_

    # Patrón de actividad diaria: más fines de semana, variación leve.
    base = {"Almuerzo": 8, "Café": 12, "Desayuno": 5, "Pan con pollo": 10, "Gaseosa": 6}

    inicio = date.today() - timedelta(days=22)
    total_vendido_dia = {}
    for i in range(22):
        dia = inicio + timedelta(days=i)
        es_fin_semana = dia.weekday() >= 5
        factor = 1.25 if es_fin_semana else 1.0

        total_vendido_dia[dia] = 0.0
        for nombre, pid_ in productos.items():
            cantidad = int(round(base[nombre] * factor * (0.85 + (i % 5) * 0.05)))
            total = _insertar_venta(nid, pid_, cantidad, precios[nombre], dia)
            total_vendido_dia[dia] += total

        # Un gasto cada 2-3 días (verduras, gas, insumos).
        if i % 2 == 0:
            _insertar_gasto(nid, "Compra de verduras", 120 + (i % 4) * 30, dia)
        if i % 3 == 0:
            _insertar_gasto(nid, "Gas / combustible", 60, dia)

    print(f"  + Caso principal generado: 22 días de actividad.")
    print(f"    Ventas de hoy: Q{sum(total_vendido_dia.values()):,.0f} (acumulado demo)")

    return nid


def hay_datos():
    """Devuelve True si ya existen negocios en la base (evita borrar producción)."""
    fila = db.query_one("SELECT COUNT(*) AS n FROM negocio")
    return int(fila["n"]) > 0


def main():
    # En producción nunca borrar la base ni duplicar datos demo si ya existen.
    if hay_datos():
        print("La base ya contiene datos. Omitiendo seed para no borrar producción.")
        print("Para re-poblar desde cero: ejecuta  python seed.py --force")
        return

    print("Poblando base de datos con datos DEMO (no reales)...")
    db.init_db(clear=True)

    print("Creando 7 negocios complementarios:")
    seed_negocios_basicos()

    print("Creando caso principal (Comedor Doña María):")
    seed_comedor_maria()

    print("\nSeed completado. La base contiene datos ficticios identificados como DEMO.")


if __name__ == "__main__":
    import sys
    # Soporte para forzar el re-poblamiento cuando se desee explícitamente.
    if "--force" in sys.argv:
        db.init_db(clear=True)
        print("Creando 7 negocios complementarios:")
        seed_negocios_basicos()
        print("Creando caso principal (Comedor Doña María):")
        seed_comedor_maria()
        print("\nSeed completado (forzado). La base contiene datos ficticios identificados como DEMO.")
    else:
        main()
