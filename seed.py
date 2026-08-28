"""Genera datos demo para GuateAyuda.

Crea 8 negocios ficticios (sección 15 del contexto). El caso principal,
Comedor Doña María, se puebla en detalle para que el dashboard y el motor
analítico tengan qué calcular. Los datos son 100% ficticios y deben
identificarse como tal (marketing demo).

Uso:
    python seed.py
"""

from datetime import date, datetime, timedelta

import db


# Marca clara de que son datos de demostración, no reales.
DEMO_TAG = "DEMO"


def _insertar_negocio(nombre, actividad, ubicacion):
    """Inserta un negocio y devuelve su id. Calcula el id numérico máximo."""
    fila = db.query_one("SELECT COALESCE(MAX(id), 0) AS max_id FROM negocio")
    nid = int(fila["max_id"]) + 1
    propietario = "María Xitumul" if "María" in nombre else "Propietario Demo"
    db.execute(
        "INSERT INTO negocio (id, nombre, propietario, actividad_principal, actividad, departamento, municipio, ubicacion) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (nid, f"{nombre} ({DEMO_TAG})", propietario, actividad, actividad, "Guatemala", ubicacion, ubicacion),
    )
    return nid


def _insertar_producto(negocio_id, nombre, precio, existencia, minimo):
    """Inserta un producto y devuelve su id."""
    fila = db.query_one("SELECT COALESCE(MAX(id), 0) AS max_id FROM producto")
    pid = int(fila["max_id"]) + 1
    db.execute(
        "INSERT INTO producto (id, negocio_id, nombre, precio_referencia, precio, existencia, inventario_minimo, minimo) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (pid, negocio_id, nombre, precio, precio, existencia, minimo, minimo),
    )
    return pid


def _insertar_venta(negocio_id, producto_id, cantidad, precio_unitario, fecha):
    """Inserta una transacción tipo venta + su detalle, devolviendo el total."""
    subtotal = cantidad * precio_unitario
    fila = db.query_one("SELECT COALESCE(MAX(id), 0) AS max_id FROM transaccion")
    tid = int(fila["max_id"]) + 1
    db.execute(
        "INSERT INTO transaccion (id, negocio_id, tipo, fecha, descripcion, monto) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, "VENTA", fecha, f"Venta (demo) de {cantidad} unidades", subtotal),
    )
    db.execute(
        "INSERT INTO detalle_venta "
        "(id, negocio_id, transaccion_id, producto_id, cantidad, precio_unitario, subtotal) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, tid, producto_id, cantidad, precio_unitario, subtotal),
    )
    return subtotal


def _insertar_gasto(negocio_id, descripcion, monto, fecha):
    """Inserta una transacción tipo gasto."""
    fila = db.query_one("SELECT COALESCE(MAX(id), 0) AS max_id FROM transaccion")
    tid = int(fila["max_id"]) + 1
    db.execute(
        "INSERT INTO transaccion (id, negocio_id, tipo, fecha, descripcion, monto) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (tid, negocio_id, "GASTO", fecha, f"{descripcion} (demo)", monto),
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

    productos = {
        _insertar_producto(nid, "Almuerzo", 25, 40, 10): "Almuerzo",
        _insertar_producto(nid, "Café", 12, 80, 30): "Café",
        _insertar_producto(nid, "Desayuno", 20, 25, 8): "Desayuno",
        _insertar_producto(nid, "Pan con pollo", 15, 50, 15): "Pan con pollo",
        _insertar_producto(nid, "Gaseosa", 10, 12, 15): "Gaseosa",
    }

    # Patrón de actividad diaria: más fines de semana, variación leve.
    base = {
        "Almuerzo": 8,
        "Café": 12,
        "Desayuno": 5,
        "Pan con pollo": 10,
        "Gaseosa": 6,
    }

    inicio = date.today() - timedelta(days=22)
    total_vendido_dia = {}
    for i in range(22):
        dia = inicio + timedelta(days=i)
        es_fin_semana = dia.weekday() >= 5
        factor = 1.25 if es_fin_semana else 1.0

        total_vendido_dia[dia] = 0.0
        for pid, nombre in productos.items():
            cantidad = int(round(base[nombre] * factor * (0.85 + (i % 5) * 0.05)))
            precio = [25, 12, 20, 15, 10][list(productos.keys()).index(pid)]
            total = _insertar_venta(nid, pid, cantidad, precio, dia)
            total_vendido_dia[dia] += total

        # Un gasto cada 2-3 días (verduras, gas, insumos).
        if i % 2 == 0:
            _insertar_gasto(nid, "Compra de verduras", 120 + (i % 4) * 30, dia)
        if i % 3 == 0:
            _insertar_gasto(nid, "Gas / combustible", 60, dia)

    print(f"  + {productos[list(productos.keys())[0]]}..."  # placeholder
          f" Caso principal generado: 22 días de actividad.")
    print(f"    Ventas de hoy: Q{sum(total_vendido_dia.values()):,.0f} (acumulado demo)")

    return nid


def main():
    print("Poblando base de datos con datos DEMO (no reales)...")
    db.init_db(clear=True)

    print("Creando 7 negocios complementarios:")
    seed_negocios_basicos()

    print("Creando caso principal (Comedor Doña María):")
    seed_comedor_maria()

    print("\nSeed completado. La base contiene datos ficticios identificados como DEMO.")


if __name__ == "__main__":
    main()
