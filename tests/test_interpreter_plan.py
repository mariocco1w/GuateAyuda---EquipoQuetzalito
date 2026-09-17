"""Tests del intérprete reestructurado (plan de mejora: INTENCIÓN + ENTIDADES).

Cubre los 12 casos positivos (sección 23), casos negativos (sección 24),
compras/proveedor, unidades, números escritos, multi-operaciones y la
relajación de la regla fundamental del producto (el producto es una entidad
independiente, nunca la frase completa).
"""

import pytest

from interpreter import interpretar, interpretar_multiples


# ---------------------------------------------------------------------------
# Sección 23: casos positivos obligatorios
# ---------------------------------------------------------------------------

def test_caso1_vendi_pinas():
    r = interpretar("Vendí 120 piñas a Q12")
    assert r["interpretado"] is True
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["producto"] == "pina"
    assert op["cantidad"] == 120
    assert op["precio_unitario"] == 12


def test_caso2_a_jose_vendi_pinas():
    r = interpretar("A José le vendí 120 piñas a Q12")
    assert r["interpretado"] is True
    op = r["operacion"]
    assert op["cliente"] == "Jose"
    assert op["producto"] == "pina"
    assert op["cantidad"] == 120
    assert op["precio_unitario"] == 12


def test_caso3_le_vendi_sandias_maria():
    r = interpretar("Le vendí 50 sandías a María")
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["cliente"] == "Maria"
    assert op["producto"] == "sandia"
    assert op["cantidad"] == 50


def test_caso4_vendi_zanahorias_carlos():
    r = interpretar("Vendí 20 zanahorias a Carlos")
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["cliente"] == "Carlos"
    assert op["producto"] == "zanahoria"
    assert op["cantidad"] == 20


def test_caso5_maria_compro_tomates():
    r = interpretar("María compró 30 tomates")
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["cliente"] == "Maria"
    assert op["producto"] == "tomate"
    assert op["cantidad"] == 30


def test_caso6_pinas_golden_precio_cada():
    r = interpretar("Vendí 10 piñas golden a José por Q15 cada una")
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["cliente"] == "Jose"
    assert op["producto"] == "pina golden"
    assert op["cantidad"] == 10
    assert op["precio_unitario"] == 15


def test_caso7_almacen_de_jose():
    r = interpretar("Vendí 25 tomates al almacén de José")
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["producto"] == "tomate"
    assert op["cantidad"] == 25
    assert "almacen" in (op["cliente"] or "").lower()
    assert "jose" in (op["cliente"] or "").lower()


def test_caso8_jose_me_compro_sandias():
    r = interpretar("José me compró 100 sandías")
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["cliente"] == "Jose"
    assert op["producto"] == "sandia"
    assert op["cantidad"] == 100


def test_caso9_compre_don_pedro():
    r = interpretar("Compré 100 tomates a Don Pedro")
    assert r["tipo"] == "compra"
    op = r["operacion"]
    assert op["proveedor"] == "Don pedro"
    assert op["producto"] == "tomate"
    assert op["cantidad"] == 100


def test_caso10_compre_don_pedro_precio():
    r = interpretar("Compré 100 tomates a Don Pedro a Q5")
    assert r["tipo"] == "compra"
    op = r["operacion"]
    assert op["proveedor"] == "Don pedro"
    assert op["producto"] == "tomate"
    assert op["cantidad"] == 100
    assert op["precio_unitario"] == 5


def test_caso11_cajas_de_tomates():
    r = interpretar("Vendí 5 cajas de tomates a Q80")
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["producto"] == "tomate"
    assert op["cantidad"] == 5
    assert op["unidad"] == "cajas"
    assert op["precio_unitario"] == 80


def test_caso12_multiples_ventas():
    rs = interpretar_multiples("Vendí 10 piñas a José y 20 sandías a María")
    ventas = [r for r in rs if r.get("interpretado")]
    assert len(ventas) == 2
    assert ventas[0]["operacion"]["cliente"] == "Jose"
    assert ventas[0]["operacion"]["producto"] == "pina"
    assert ventas[0]["operacion"]["cantidad"] == 10
    assert ventas[1]["operacion"]["cliente"] == "Maria"
    assert ventas[1]["operacion"]["producto"] == "sandia"
    assert ventas[1]["operacion"]["cantidad"] == 20


# ---------------------------------------------------------------------------
# Sección 24: casos negativos (no crear productos contaminados)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase", [
    "A José",
    "José 120",
    "José piñas",
    "piñas José",
    "piñas Q12",
    "120 piñas",
    "piñas 120",
    "maria le zanahorias su puesto",
    "hernesto le sandias",
    "piñas almacen",
    "piñas x 12",
    "A Jose le 120 x 12",
])
def test_casos_negativos_no_producto(frase):
    r = interpretar(frase)
    assert r["interpretado"] is False
    assert (r.get("operacion") or {}).get("producto") in (None, "")


# ---------------------------------------------------------------------------
# Expresiones conversacionales de venta (sección 6)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase,cliente,producto,cantidad", [
    ("Me compraron 50 tomates", None, "tomate", 50),
    ("José se llevó 20 piñas", "Jose", "pina", 20),
    ("Hoy salieron 100 sandías", None, "sandia", 100),
    ("Hoy salieron 25 sandías", None, "sandia", 25),
])
def test_expresiones_venta(frase, cliente, producto, cantidad):
    r = interpretar(frase)
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["producto"] == producto
    assert op["cantidad"] == cantidad
    if cliente:
        assert op["cliente"] == cliente


# ---------------------------------------------------------------------------
# Números escritos y unidades (secciones 11 y 12)
# ---------------------------------------------------------------------------

def test_numeros_escritos():
    r = interpretar("Vendí veinte piñas a doce quetzales")
    assert r["tipo"] == "venta"
    assert r["operacion"]["cantidad"] == 20
    assert r["operacion"]["precio_unitario"] == 12


def test_una_docena():
    r = interpretar("Vendí una docena de rosas a 30 quetzales")
    assert r["tipo"] == "venta"
    assert r["operacion"]["cantidad"] == 12
    assert r["operacion"]["producto"] == "rosas"


def test_cantidades_escritas_y_precio_cada():
    r = interpretar("Vendí 10 piñas a José por Q15 cada una")
    assert r["operacion"]["cantidad"] == 10
    assert r["operacion"]["precio_unitario"] == 15


# ---------------------------------------------------------------------------
# Compatibilidad y estructura interna (secciones 3 y 22)
# ---------------------------------------------------------------------------

def test_estructura_interna_intent():
    r = interpretar("Vendí 120 piñas a Q12")
    assert r["intent"] == "SALE"
    est = r["estructura"]
    assert est["product"] == "pina"
    assert est["quantity"] == 120
    assert est["unit_price"] == 12
    assert est["confidence"] > 0


def test_estructura_interna_compra():
    r = interpretar("Compré 100 tomates a Don Pedro a Q5")
    assert r["intent"] == "PURCHASE"
    est = r["estructura"]
    assert est["supplier"] == "Don pedro"
    assert est["product"] == "tomate"
    assert est["quantity"] == 100
    assert est["customer"] is None


def test_no_guarda_lenguaje_natural_en_producto():
    # La regla fundamental: el producto solo es el fragmento semántico PRODUCT.
    r = interpretar("A José le vendí 120 piñas a Q12")
    assert r["operacion"]["producto"] == "pina"


# ---------------------------------------------------------------------------
# Consultas (secciones 2 y 21): SALES_QUERY, PURCHASE_QUERY, PRODUCT_QUERY,
# INVENTORY_QUERY
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase,tipo", [
    ("¿Cuánto vendí hoy?", "ventas"),
    ("¿Cuántas ventas hice esta semana?", "ventas"),
    ("¿Que he vendido?", "ventas"),
    ("¿Cuánto gasté en compras este mes?", "gastos"),
    ("¿Cuánto gasté?", "gastos"),
    ("¿Cuál es mi producto más vendido?", "productos"),
    ("¿Qué productos tengo?", "productos"),
    ("¿Cuántas piñas me quedan?", "inventario"),
    ("¿Qué me queda?", "inventario"),
    ("¿Cómo está mi inventario?", "inventario"),
    ("¿Cómo está mi inventario?", "inventario"),
    ("¿Cuánto le vendí a José?", "ventas"),
])
def test_consultas_varios_tipos(frase, tipo):
    r = interpretar(frase)
    assert r.get("consulta") is True, frase
    assert r["tipo"] == tipo, frase


def test_consulta_inventario_no_es_registro():
    r = interpretar("¿Cuántas piñas me quedan?")
    assert r["consulta"] is True
    assert r["tipo"] == "inventario"
    assert not r.get("operacion")


def test_registro_inventario_sigue_siendo_registro():
    r = interpretar("Tengo 10 gaseosas")
    assert r["tipo"] == "inventario"
    assert not r.get("consulta")


# ---------------------------------------------------------------------------
# Expresiones de venta conversacionales (sección 6)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase,cliente,producto,cantidad", [
    ("Le vendí 20 piñas a José", "Jose", "pina", 20),
    ("A José le vendí 20 piñas", "Jose", "pina", 20),
    ("José se llevó 20 piñas", "Jose", "pina", 20),
    ("Hoy salieron 20 piñas para José", "Jose", "pina", 20),
    ("Hoy salieron 100 sandías", None, "sandia", 100),
    ("Me compraron 50 tomates", None, "tomate", 50),
    ("Me compró 30 aguacates", None, "aguacate", 30),
    ("Despaché 15 mangos", None, "mango", 15),
    ("Entregué 25 plátanos", None, "platano", 25),
    ("Coloqué 10 granadillas", None, "granadillas", 10),
])
def test_expresiones_venta_conversacionales(frase, cliente, producto, cantidad):
    r = interpretar(frase)
    assert r["tipo"] == "venta", frase
    op = r["operacion"]
    assert op["producto"] == producto, frase
    assert op["cantidad"] == cantidad, frase
    if cliente:
        assert op["cliente"] == cliente, frase


# ---------------------------------------------------------------------------
# Expresiones de compra conversacionales (sección 7)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase,proveedor,producto,cantidad", [
    ("Compré 100 tomates a Don Pedro a Q5", "Don pedro", "tomate", 100),
    ("Adquirí 50 naranjas al almacén", "Almacen", "naranja", 50),
    ("Conseguí 30 repollos a Q3", None, "repollo", 30),
    ("Pedí 20 lechugas a María", "Maria", "lechuga", 20),
    ("Encargué 15 cebollas", None, "cebolla", 15),
])
def test_expresiones_compra(frase, proveedor, producto, cantidad):
    r = interpretar(frase)
    assert r["tipo"] == "compra", frase
    op = r["operacion"]
    assert op["producto"] == producto, frase
    assert op["cantidad"] == cantidad, frase
    if proveedor:
        assert (op["proveedor"] or "").lower() == proveedor.lower(), frase


# ---------------------------------------------------------------------------
# Productos de varias palabras (sección 13)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase,producto", [
    ("Vendí 10 piñas golden a José", "pina golden"),
    ("Vendí 5 cajas de tomate cherry", "tomate cherry"),
    ("Vendí 8 queso fresco a María", "queso"),
    ("Compré 3 café molido a Don Pedro", "cafe"),
    ("Vendí 12 agua pura", "agua"),
])
def test_productos_de_varias_palabras(frase, producto):
    r = interpretar(frase)
    assert r["interpretado"] is True, frase
    assert r["operacion"]["producto"] == producto, frase


# ---------------------------------------------------------------------------
# Números escritos y variantes (secciones 1 y 11)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase,cantidad", [
    ("Vendí veinte mil piñas a Q12", 20000),
    ("Vendí trescientos tomates", 300),
    ("Vendi quinientos aguacates", 500),
    ("Compré doscientos repollos", 200),
    ("Vendí treinta y cinco sandías", 35),
    ("Vendí cuarenta y cinco aguacates", 45),
])
def test_numeros_escritos_compuestos(frase, cantidad):
    r = interpretar(frase)
    assert r["interpretado"] is True, frase
    assert r["operacion"]["cantidad"] == cantidad, frase


def test_normalizacion_tildes_y_mayusculas():
    r1 = interpretar("VENDÍ 20 PIÑAS A Q12")
    r2 = interpretar("vendí 20 piñas a q12")
    r3 = interpretar("Vendí 20 piñas a 12 quetzales")
    for r in (r1, r2, r3):
        assert r["operacion"]["producto"] == "pina"
        assert r["operacion"]["cantidad"] == 20
        assert r["operacion"]["precio_unitario"] == 12


def test_variant_vendi_sin_tilde_vs_con_tilde():
    r = interpretar("Vendi 5 cafés a 10 quetzales")
    assert r["tipo"] == "venta"
    assert r["operacion"]["cantidad"] == 5
    assert r["operacion"]["producto"] == "cafe"


# ---------------------------------------------------------------------------
# Precios (sección 10)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase,precio", [
    ("Vendí 10 piñas a José por Q15 cada una", 15),
    ("Vendí 10 piñas a 12 quetzales", 12),
    ("Vendí 10 piñas por 12 quetzales", 12),
    ("Vendí 10 piñas Q12 cada uno", 12),
    ("Vendí 10 piñas a Q12 la unidad", 12),
    ("Compré 10 tomates a Q5 por unidad", 5),
])
def test_variantes_precio(frase, precio):
    r = interpretar(frase)
    assert r["interpretado"] is True, frase
    assert r["operacion"]["precio_unitario"] == precio, frase


# ---------------------------------------------------------------------------
# Unidades de medida (sección 12)
# ---------------------------------------------------------------------------

def test_unidades_varias():
    r = interpretar("Vendí 10 cajas de tomates")
    assert r["operacion"]["cantidad"] == 10
    assert r["operacion"]["unidad"] == "cajas"
    assert r["operacion"]["producto"] == "tomate"

    r2 = interpretar("Vendí 5 libras de frijol")
    assert r2["operacion"]["cantidad"] == 5
    assert r2["operacion"]["unidad"] == "libras"
    assert r2["operacion"]["producto"] == "frijol"


def test_media_docena():
    r = interpretar("Vendí media docena de rosas")
    assert r["operacion"]["cantidad"] == 6
    assert r["operacion"]["producto"] == "rosas"


# ---------------------------------------------------------------------------
# Personas compuestas (sección 8)
# ---------------------------------------------------------------------------

def test_persona_nombre_compuesto():
    r = interpretar("Vendí 10 piñas a Juan Carlos")
    assert r["operacion"]["cliente"] == "Juan carlos"
    assert r["operacion"]["producto"] == "pina"


def test_persona_con_tratamiento():
    r = interpretar("Vendí 10 piñas a don José")
    assert r["operacion"]["cliente"] == "Don jose"
    assert r["operacion"]["producto"] == "pina"


def test_negocio_como_destino():
    r = interpretar("Vendí 120 tomates al almacén")
    assert r["operacion"]["cliente"] == "Almacen"
    assert r["operacion"]["producto"] == "tomate"
    assert not r["operacion"]["producto"].endswith("almacen")


# ---------------------------------------------------------------------------
# Estructura interna: total_price (sección 22)
# ---------------------------------------------------------------------------

def test_total_price_en_estructura():
    r = interpretar("Vendí 120 piñas a José a Q12")
    est = r["estructura"]
    assert est["total_price"] == 1440


def test_estructura_sin_total_si_falta_precio():
    r = interpretar("Vendí 20 piñas a José")
    est = r["estructura"]
    assert est["total_price"] is None


# ---------------------------------------------------------------------------
# Cliente vs proveedor según intención (sección 5)
# ---------------------------------------------------------------------------

def test_misma_persona_rol_segun_intencion():
    r_venta = interpretar("Vendí tomates a José")
    assert r_venta["operacion"]["cliente"] == "Jose"
    assert r_venta["operacion"].get("proveedor") is None

    r_compra = interpretar("Compré tomates a José")
    assert r_compra["operacion"]["proveedor"] == "Jose"
    assert r_compra["operacion"].get("cliente") is None
