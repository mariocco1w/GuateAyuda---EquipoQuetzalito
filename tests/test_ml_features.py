"""Tests de la capa de preparación de datos para ML (FASE 1).

Se usan mocks de `db` para verificar la lógica de feature engineering sin
depender de la base de datos real. Cubre:

    * Series diarias de ventas y sus indicadores (promedios, tendencia,
      crecimiento).
    * Features de demanda por producto.
    * Resumen consolidado y manejo de "no disponible".
"""

import pytest

import ml.features as features

# ---------------------------------------------------------------------------
# Mocks de la capa db
# ---------------------------------------------------------------------------


class MockDB:
    """Simula db.query según subcadenas dentro del SQL."""

    def __init__(self, query_map=None, query_one_map=None):
        self._q = query_map or {}
        self._q1 = query_one_map or {}

    def query(self, sql, params=None):
        for clave, valor in self._q.items():
            if clave in sql:
                return valor
        return []

    def query_one(self, sql, params=None):
        for clave, valor in self._q1.items():
            if clave in sql:
                return valor
        return None


def _row_dia(producto_id, nombre, dia, cantidad, total):
    return {
        "producto_id": producto_id,
        "nombre": nombre,
        "dia": dia,
        "cantidad": cantidad,
        "total": total,
    }


@pytest.fixture
def mock_db(monkeypatch):
    md = MockDB()
    monkeypatch.setattr(features, "db", md)
    return md


def test_preparar_series_diarias_vacia(mock_db):
    res = features.preparar_series_diarias(1)
    assert res.empty


def test_preparar_series_diarias_con_datos(mock_db):
    mock_db._q[features._SQL_VENTAS_DIARIAS] = [
        {"dia": "2026-08-01", "total": 100, "cantidad": 10},
        {"dia": "2026-08-02", "total": 200, "cantidad": 20},
        {"dia": "2026-08-03", "total": 150, "cantidad": 15},
    ]
    df = features.preparar_series_diarias(1)
    assert not df.empty
    assert "promedio_7" in df.columns
    assert "tendencia" in df.columns
    assert "crecimiento" in df.columns
    # El promedio de 7 días sobre la ventana: (0+0+0+0+100+200+150)/7.
    assert df["promedio_7"].iloc[-1] == pytest.approx(450.0 / 7.0)


def test_ventas_por_producto_devuelve_features(mock_db):
    mock_db._q[features._SQL_VENTAS_PRODUCTO] = [
        _row_dia(1, "Almuerzo", "2026-08-01", 8, 200),
        _row_dia(1, "Almuerzo", "2026-08-02", 12, 300),
        _row_dia(2, "Café", "2026-08-01", 15, 180),
    ]
    # Productos del negocio.
    features.db._q = {
        **mock_db._q,
        "FROM producto": [
            {"producto_id": 1, "nombre": "Almuerzo", "existencia": 40,
             "minimo": 10, "precio": 25},
            {"producto_id": 2, "nombre": "Café", "existencia": 80,
             "minimo": 10, "precio": 12},
        ],
    }
    res = features.preparar_ventas_por_producto(1)
    assert len(res) == 2
    almuerzo = next(p for p in res if p["producto_id"] == 1)
    assert almuerzo["dias_con_venta"] == 2
    assert almuerzo["ventas_totales"] == pytest.approx(500.0)
    cafe = next(p for p in res if p["producto_id"] == 2)
    assert cafe["dias_con_venta"] == 1


def test_resumen_features_disponible(mock_db):
    mock_db._q[features._SQL_VENTAS_DIARIAS] = [
        {"dia": "2026-08-01", "total": 100, "cantidad": 10},
    ]
    mock_db._q[features._SQL_MOV_INVENTARIO] = [
        {"producto_id": 1, "tipo": "SALIDA_VENTA", "salidas": 20,
         "entradas": 0, "n_movimientos": 5},
    ]
    mock_db._q["FROM producto"] = [
        {"producto_id": 1, "nombre": "Almuerzo", "existencia": 40,
         "minimo": 10, "precio": 25},
    ]
    res = features.resumen_features_negocio(1)
    assert res["disponible"] is True
    assert "inventario" in res
    assert "consumo" in res


def test_resumen_features_no_disponible(mock_db):
    res = features.resumen_features_negocio(1)
    assert res["disponible"] is False
    assert "mensaje" in res
