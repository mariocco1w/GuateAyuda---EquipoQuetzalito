"""Tests del intérprete conversacional (parser por reglas).

Verifica el control del modelo: que el lenguaje natural se traduzca
correctamente a estructura para los tres tipos de operación del MVP
(secciones 8 y 12 del contexto) y casos límite.
"""

import pytest

from interpreter import interpretar


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
    r = interpretar("buenos días")
    assert r["interpretado"] is False
    assert "No pude identificar" in r["mensaje"]


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
