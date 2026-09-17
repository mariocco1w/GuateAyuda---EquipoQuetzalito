"""Tests del vocabulario guatemalteco integrado al intérprete."""

from interpreter import interpretar
from vocabulario_productos import ALIAS_A_CANONICO, canonicalizar_producto


def test_vocabulario_cargado():
    assert len(ALIAS_A_CANONICO) > 50
    assert canonicalizar_producto("guineo") == "banano"
    assert canonicalizar_producto("guineos") == "banano"
    assert canonicalizar_producto("guisquiles") == "guisquil"
    assert canonicalizar_producto("chuchitos") == "chuchito"
    assert canonicalizar_producto("quetzaltecas") == "quetzaltecas"


def test_compra_guineo_como_banano():
    r = interpretar("Compré 3 cajas de guineo")
    assert r["interpretado"] is True
    assert r["tipo"] == "compra"
    assert r["operacion"]["producto"] == "banano"
    assert r["operacion"]["cantidad"] == 3
    assert r["operacion"]["unidad"] in ("cajas", "caja")


def test_inventario_guisquiles():
    r = interpretar("Tengo 50 güisquiles")
    assert r["interpretado"] is True
    assert r["tipo"] == "inventario"
    assert r["operacion"]["producto"] == "guisquil"
    assert r["operacion"]["existencia"] == 50


def test_produccion_chuchitos():
    r = interpretar("Produje 100 chuchitos")
    assert r["interpretado"] is True
    assert r["tipo"] == "produccion"
    assert r["operacion"]["producto"] == "chuchito"
    assert r["operacion"]["cantidad"] == 100


def test_venta_panes():
    r = interpretar("Vendí 10 panes a Q2 cada uno")
    assert r["interpretado"] is True
    assert r["tipo"] == "venta"
    assert r["operacion"]["producto"] == "pan"
    assert r["operacion"]["cantidad"] == 10
    assert r["operacion"]["precio_unitario"] == 2


def test_ortografia_guicoy_pepian():
    r1 = interpretar("Vendí 8 guicoyes a Q5")
    assert r1["operacion"]["producto"] == "guicoy"
    r2 = interpretar("Vendí 5 pepian a Q20")
    assert r2["operacion"]["producto"] == "pepian"


def test_alias_maya_tomate():
    r = interpretar("Compré 20 pix a Q2")
    assert r["interpretado"] is True
    assert r["operacion"]["producto"] == "tomate"
