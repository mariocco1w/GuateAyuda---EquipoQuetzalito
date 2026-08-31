"""Tests del intérprete conversacional (parser por reglas).

Verifica el control del modelo: que el lenguaje natural se traduzca
correctamente a estructura para los tres tipos de operación del MVP
(secciones 8 y 12 del contexto) y casos límite.
"""

import pytest

from interpreter import interpretar, interpretar_multiples


def test_venta_almuerzos():
    r = interpretar("Vendí 8 almuerzos a Q25")
    assert r["interpretado"] is True
    assert r["tipo"] == "venta"
    op = r["operacion"]
    assert op["producto"] == "almuerzos"
    assert op["cantidad"] == 8
    assert op["precio_unitario"] == 25
    # El intérprete NO calcula el total (lo hace el backend).
    assert "total" not in op


def test_venta_cafe():
    r = interpretar("Vendi 5 cafés a Q12")
    assert r["interpretado"] is True
    assert r["tipo"] == "venta"
    assert r["operacion"]["cantidad"] == 5
    assert r["operacion"]["precio_unitario"] == 12


def test_venta_con_palabras():
    r = interpretar("Hoy vendí diez panes con pollo a quince quetzales cada uno")
    # "diez" y "quince" son palabras, no números; el parser numérico no las lee.
    assert r["interpretado"] is False or r["operacion"]["cantidad"] is None


def test_gasto_verduras():
    r = interpretar("Gasté Q150 comprando verduras")
    assert r["interpretado"] is True
    assert r["tipo"] == "gasto"
    assert r["operacion"]["monto"] == 150


def test_inventario_gaseosas():
    r = interpretar("Me quedan 10 gaseosas")
    assert r["interpretado"] is True
    assert r["tipo"] == "inventario"
    assert r["operacion"]["existencia"] == 10
    assert r["operacion"]["producto"] == "gaseosas"


def test_mensaje_vacio():
    r = interpretar("")
    assert r["interpretado"] is False


def test_sin_operacion_reconocible():
    r = interpretar("mañana lloverá con seguridad")
    assert r["interpretado"] is False
    assert "No pude identificar" in r["mensaje"]


def test_saludo_es_consulta():
    r = interpretar("Hola")
    assert r["interpretado"] is True
    assert r["consulta"] is True
    assert r["tipo"] == "saludo"
    assert r["token_sesion"] is None


def test_consulta_productos():
    r = interpretar("¿Qué productos tengo?")
    assert r["interpretado"] is True
    assert r["consulta"] is True
    assert r["tipo"] == "productos"


def test_consulta_ventas():
    r = interpretar("¿Cómo van mis ventas?")
    assert r["consulta"] is True
    assert r["tipo"] == "ventas"


def test_consulta_gastos():
    r = interpretar("¿Cuánto he gastado este mes?")
    assert r["consulta"] is True
    assert r["tipo"] == "gastos"


def test_consulta_inventario():
    r = interpretar("¿Qué me queda?")
    assert r["consulta"] is True
    assert r["tipo"] == "inventario"


def test_consulta_resumen():
    r = interpretar("Dame un resumen de mi negocio")
    assert r["consulta"] is True
    assert r["tipo"] == "resumen"


def test_consulta_ayuda():
    r = interpretar("¿Qué puedes hacer?")
    assert r["consulta"] is True
    assert r["tipo"] == "ayuda"


def test_registro_inventario_no_es_consulta():
    r = interpretar("Tengo 10 gaseosas")
    assert r["interpretado"] is True
    assert not r.get("consulta")
    assert r["tipo"] == "inventario"


def test_saludo_no_roba_la_venta():
    rs = interpretar_multiples("Buenos días, vendí 8 almuerzos a Q25")
    no_saludos = [r for r in rs if not (r.get("consulta") and r["tipo"] == "saludo")]
    assert len(no_saludos) == 1
    assert no_saludos[0]["tipo"] == "venta"
    assert not no_saludos[0].get("consulta")


def test_interpretador_genera_token():
    r = interpretar("Vendí 2 cafés a Q10")
    assert r["token_sesion"]
    r2 = interpretar("Vendí 3 cafés a Q10")
    assert r["token_sesion"] != r2["token_sesion"]


def test_no_calcula_ni_modifica_datos():
    # El intérprete solo extrae; no debe contener el total calculado.
    r = interpretar("Vendí 10 panes con pollo a 15 quetzales cada uno")
    op = r["operacion"]
    assert "total" not in op


def test_produccion_vasos():
    r = interpretar("Se fabricaron 24 unidades de vasos")
    assert r["interpretado"] is True
    assert r["tipo"] == "produccion"
    assert r["operacion"]["cantidad"] == 24
    assert r["operacion"]["producto"] == "vasos"


def test_ingreso_inventario_espejos():
    r = interpretar("Hoy ingresaron 15 espejos")
    assert r["interpretado"] is True
    assert r["tipo"] == "inventario"
    assert r["operacion"]["movimiento"] == "ENTRADA"
    assert r["operacion"]["existencia"] == 15
    assert r["operacion"]["producto"] == "espejos"


def test_multiples_operaciones():
    rs = interpretar_multiples("el dia de hoy ingresaron 15 espejos y se fabricaron 24 unidades de vasos")
    interpretados = [r for r in rs if r.get("interpretado")]
    assert len(interpretados) == 2
    assert interpretados[0]["tipo"] == "inventario"
    assert interpretados[0]["operacion"]["movimiento"] == "ENTRADA"
    assert interpretados[1]["tipo"] == "produccion"
    assert interpretados[1]["operacion"]["producto"] == "vasos"


def test_multiples_simple_unica():
    # Un solo tipo de operación sigue funcionando y devuelve lista de 1.
    rs = interpretar_multiples("Vendí 8 almuerzos a Q25")
    assert len(rs) == 1
    assert rs[0]["interpretado"] is True
    assert rs[0]["tipo"] == "venta"


def test_multiples_texto_largo():
    # Mensaje largo y conversacional con dos operaciones en una sola oración.
    rs = interpretar_multiples(
        "El día de hoy me ingresaron 20 tortillas y vendí una cantidad de 35 gaseosas"
    )
    interpretados = [r for r in rs if r.get("interpretado")]
    assert len(interpretados) == 2
    inv = [r for r in interpretados if r["tipo"] == "inventario"][0]["operacion"]
    venta = [r for r in interpretados if r["tipo"] == "venta"][0]["operacion"]
    assert inv["movimiento"] == "ENTRADA"
    assert inv["existencia"] == 20
    assert inv["producto"] == "tortillas"
    assert venta["cantidad"] == 35
    assert venta["producto"] == "gaseosas"


def test_multiples_frase_con_semicolon_venden():
    rs = interpretar_multiples("Gasté Q20 en panes; y vendí 5 gaseosas a Q3")
    interpretados = [r for r in rs if r.get("interpretado")]
    assert len(interpretados) == 2
    tipos = {r["tipo"] for r in interpretados}
    assert tipos == {"gasto", "venta"}


def test_consulta_asesor():
    for msg in ("¿Quién eres?", "¿Quién te creó?", "¿Cómo te llamas?", "Eres un bot"):
        r = interpretar(msg)
        assert r["consulta"] is True, msg
        assert r["tipo"] == "asesor", msg


def test_consulta_despedida():
    for msg in ("Gracias", "muchas gracias", "adios", "hasta luego"):
        r = interpretar(msg)
        assert r["consulta"] is True, msg
        assert r["tipo"] == "despedida", msg
