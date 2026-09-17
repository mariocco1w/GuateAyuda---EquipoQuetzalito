"""Tests de la predicción de ventas (FASE 2).

Se usan mocks de `db` para verificar la lógica sin depender de datos reales.
Cubre:

    * Pronóstico por producto (modelo ML cuando hay historial suficiente).
    * Fallback estadístico cuando faltan días.
    * "Sin datos" cuando no hay historial.
    * Pronóstico del negocio agregado.
    * Registro en insight_ia y consulta de última predicción.
"""

import json

import pytest

import ml.forecasting as fore
import ml.features as feat
from ml.features import _SQL_VENTAS_PRODUCTO


class MockDB:
    """Simula db.query / db.query_one / db.execute."""

    def __init__(self, query_map=None, query_one_map=None):
        self._q = query_map or {}
        self._q1 = query_one_map or {}
        self.executado = []

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

    def execute(self, sql, params=None):
        self.executado.append(sql)
        return 1


def _fila_venta(pid, dia, cantidad, total):
    return {"producto_id": pid, "nombre": f"P{pid}", "dia": dia,
            "cantidad": cantidad, "total": total}


def _productos(n=2):
    return [
        {"producto_id": i, "nombre": f"P{i}", "existencia": 50,
         "minimo": 10, "precio": 25}
        for i in range(1, n + 1)
    ]


def _generar_series(pid, n_dias=20, base=100.0):
    """Genera `n_dias` filas de ventas diarias para un producto."""
    from datetime import date, timedelta
    inicio = date.today() - timedelta(days=n_dias)
    return [
        _fila_venta(pid, (inicio + timedelta(days=i)).isoformat(),
                    cantidad=5 + (i % 3), total=base + (i % 5) * 10.0)
        for i in range(n_dias)
    ]


@pytest.fixture
def mock_db(monkeypatch):
    md = MockDB()
    monkeypatch.setattr(fore, "db", md)
    monkeypatch.setattr(feat, "db", md)
    return md


def test_pronostico_sin_datos(mock_db):
    res = fore.pronostico_producto(1, 1, "P1", dias=7)
    assert res["disponible"] is False
    assert res["estado"] == "sin_datos"


def test_pronostico_fallback_estadistico(mock_db):
    # Solo 3 días -> fallback (menos de MIN_DIAS_MODELO).
    mock_db._q = {
        _SQL_VENTAS_PRODUCTO: _generar_series(1, n_dias=3),
    }
    res = fore.pronostico_producto(1, 1, "P1", dias=7)
    assert res["estado"] == "fallback_estadistico"
    assert res["modelo"] == fore.MODELO_FALLBACK
    assert "Datos insuficientes" in res["mensaje"]
    assert len(res["predicciones"]) == 7
    assert res["disponible"] is False


def test_pronostico_modelo_ml(mock_db):
    mock_db._q = {
        _SQL_VENTAS_PRODUCTO: _generar_series(1, n_dias=20),
    }
    res = fore.pronostico_producto(1, 1, "P1", dias=7)
    assert res["estado"] == "modelo_ml"
    assert res["disponible"] is True
    assert res["modelo"] == fore.MODELO_NOMBRE
    assert len(res["predicciones"]) == 7
    assert "rmse_entrenamiento" in res["metricas"]
    assert res["metricas"]["mae_holdout"] >= 0


def test_pronostico_negocio_agrega_productos(mock_db):
    # Dos productos con 20 días de datos.
    series = _generar_series(1, n_dias=20) + _generar_series(2, n_dias=20)
    mock_db._q = {
        _SQL_VENTAS_PRODUCTO: series,
        "FROM producto": _productos(n=2),
    }
    res = fore.pronostico_negocio(1, dias=5)
    assert res["disponible"] is True
    assert res["estado"] == "modelo_ml"
    assert len(res["predicciones"]) == 5
    assert len(res["por_producto"]) == 2


def test_pronostico_negocio_sin_datos(mock_db):
    mock_db._q = {"FROM producto": _productos(n=2)}
    res = fore.pronostico_negocio(1, dias=5)
    assert res["disponible"] is False
    assert res["estado"] == "sin_datos"


def test_registrar_prediccion(mock_db):
    res = {
        "disponible": True,
        "estado": "modelo_ml",
        "negocio_id": 1,
        "modelo": fore.MODELO_NOMBRE,
        "periodo_dias": 7,
        "predicciones": [{"dia": "2026-09-04", "estimado": 100.0}],
        "por_producto": [],
        "mensaje": "ok",
    }
    assert fore.registrar_prediccion(1, res) is True
    assert len(mock_db.executado) == 2  # DELETE + INSERT
    # El INSERT incluye evidencia JSON.
    assert "INSERT INTO insight_ia" in mock_db.executado[1]


def test_registrar_prediccion_no_disponible(mock_db):
    assert fore.registrar_prediccion(1, {"disponible": False,
                                         "predicciones": []}) is False
    assert mock_db.executado == []


def test_ultima_prediccion(mock_db):
    evidencia = {"predicciones": [{"dia": "2026-09-04", "estimado": 100.0}]}
    mock_db._q = {
        "WHERE negocio_id =": [
            {
                "negocio_id": 1,
                "titulo": "Predicción de ventas",
                "descripcion": "ok",
                "evidencia": json.dumps(evidencia),
                "modelo": fore.MODELO_NOMBRE,
                "confidence": 0.7,
                "generado_en": "2026-09-04T10:00:00",
                "expira_en": "2026-09-11",
            }
        ]
    }
    ult = fore.ultima_prediccion(1)
    assert ult is not None
    assert ult["modelo"] == fore.MODELO_NOMBRE
    assert ult["evidencia"]["predicciones"][0]["estimado"] == 100.0