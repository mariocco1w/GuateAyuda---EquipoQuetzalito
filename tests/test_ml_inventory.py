"""Tests del análisis de inventario (FASE 3).

Cubre:

    * Análisis con demanda ML estimada (riesgo, días hasta agotamiento,
      reposición sugerida).
    * Productos sin historial de ventas (sin_datos / bajo mínimo).
    * Productos por agotarse (filtro por riesgo mínimo).
"""

import pytest

import ml.forecasting as fore
import ml.features as feat
import ml.inventory as inv
from ml.features import _SQL_VENTAS_PRODUCTO


class MockDB:
    """Simula db.query / db.query_one / db.execute."""

    def __init__(self, query_map=None):
        self._q = query_map or {}
        self.executado = []

    def query(self, sql, params=None):
        for clave, valor in self._q.items():
            if clave in sql:
                return valor
        return []

    def query_one(self, sql, params=None):
        for clave, valor in self._q.items():
            if clave in sql:
                return valor
        return None

    def execute(self, sql, params=None):
        self.executado.append(sql)
        return 1


def _fila_venta(pid, dia, cantidad, total):
    return {"producto_id": pid, "nombre": f"P{pid}", "dia": dia,
            "cantidad": cantidad, "total": total}


def _generar_series(pid, n_dias=20, unidades=8.0):
    from datetime import date, timedelta
    inicio = date.today() - timedelta(days=n_dias)
    return [
        _fila_venta(pid, (inicio + timedelta(days=i)).isoformat(),
                    cantidad=unidades, total=unidades * 25)
        for i in range(n_dias)
    ]


@pytest.fixture
def mock_db(monkeypatch):
    md = MockDB()
    monkeypatch.setattr(fore, "db", md)
    monkeypatch.setattr(feat, "db", md)
    return md


def _productos(con_existencia):
    return [
        {
            "producto_id": pid,
            "nombre": f"P{pid}",
            "existencia": existencia,
            "minimo": minimo,
            "precio": 25,
        }
        for pid, existencia, minimo in con_existencia
    ]


def test_analisis_inventario_riesgo_alto(mock_db):
    # Producto 1: demanda 8/día, existencia 40 -> se agota en ~5 días (ALTO).
    series = _generar_series(1, n_dias=20, unidades=8)
    mock_db._q = {
        _SQL_VENTAS_PRODUCTO: series,
        "FROM producto": _productos([(1, 40.0, 10.0)]),
    }
    r = inv.analisis_inventario(1, dias=7)
    assert r["disponible"] is True
    prod = r["productos"][0]
    assert prod["riesgo"] == "ALTO"
    assert prod["consumo_diario"] == pytest.approx(8.0, abs=0.5)
    assert prod["dias_hasta_agotamiento"] == pytest.approx(
        40.0 / prod["consumo_diario"], rel=0.2)
    assert prod["reposicion_sugerida"] > 0


def test_analisis_inventario_sin_historial_bajo_minimo(mock_db):
    # Sin ventas, pero producto ya está por debajo del mínimo -> ALTO.
    mock_db._q = {
        "FROM producto": _productos([(1, 5.0, 10.0)]),
    }
    r = inv.analisis_inventario(1, dias=7)
    prod = r["productos"][0]
    assert prod["riesgo"] == "ALTO"
    assert prod["reposicion_sugerida"] == pytest.approx(5.0)
    assert prod["estado_prediccion"] == "sin_datos"


def test_analisis_inventario_sin_historial_ok(mock_db):
    mock_db._q = {
        "FROM producto": _productos([(1, 40.0, 10.0)]),
    }
    r = inv.analisis_inventario(1, dias=7)
    prod = r["productos"][0]
    assert prod["riesgo"] == "BAJO"
    assert prod["reposicion_sugerida"] is None


def test_productos_por_agotarse_filtra(mock_db):
    series = _generar_series(1, n_dias=20, unidades=8)
    mock_db._q = {
        _SQL_VENTAS_PRODUCTO: series,
        "FROM producto": _productos([(1, 40.0, 10.0)], ) + _productos([(2, 500.0, 50.0)]),
    }
    # El producto 1 (ALTO) debe aparecer; el 2 tiene mucho stock -> no.
    res = inv.productos_por_agotarse(1, dias=7, riesgo_minimo="MEDIO")
    nombres = [p["producto"] for p in res]
    assert "P1" in nombres
    assert "P2" not in nombres


def test_analisis_no_modifica_datos(mock_db):
    # No debe haber ninguna escritura (solo lecturas).
    mock_db._q = {
        _SQL_VENTAS_PRODUCTO: _generar_series(1, n_dias=20, unidades=8),
        "FROM producto": _productos([(1, 40.0, 10.0)]),
    }
    inv.analisis_inventario(1, dias=7)
    assert mock_db.executado == []