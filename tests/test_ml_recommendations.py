"""Tests del motor de recomendaciones (FASE 5).

Cubre:

    * Recomendaciones de inventario (riesgo ALTO).
    * Recomendaciones por tendencia (baja de ventas).
    * Recomendaciones por predicción.
    * Recomendaciones por anomalías.
    * Recomendaciones financieras (gastos/ventas, sin "ganancia").
    * Orden por prioridad y persistencia en insight_ia.
"""

import json

import pytest

import analytics.engine as aengine
import ml.anomaly as anomaly
import ml.features as feat
import ml.forecasting as fore
import ml.recommendations as reco


class MockDB:
    """Simula db.query / db.query_one / db.execute."""

    def __init__(self, query_map=None, query_one_map=None):
        # Ordenar por longitud para que claves más específicas matchen primero.
        self._q = dict(sorted((query_map or {}).items(),
                              key=lambda kv: len(kv[0]), reverse=True))
        self._q1 = dict(sorted((query_one_map or {}).items(),
                               key=lambda kv: len(kv[0]), reverse=True))
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


def _generar_series(pid, n_dias=20, unidades=8.0, total=None):
    from datetime import date, timedelta
    inicio = date.today() - timedelta(days=n_dias)
    return [
        _fila_venta(pid, (inicio + timedelta(days=i)).isoformat(),
                    cantidad=unidades,
                    total=total if total is not None else unidades * 25)
        for i in range(n_dias)
    ]


@pytest.fixture
def mock_db(monkeypatch):
    md = MockDB()
    monkeypatch.setattr(reco, "db", md)
    monkeypatch.setattr(fore, "db", md)
    monkeypatch.setattr(feat, "db", md)
    monkeypatch.setattr(anomaly, "db", md)
    monkeypatch.setattr(aengine, "db", md)
    return md


def _datos_comedor():
    """Configura datos tipo Comedor: 5 productos con 20 días de venta."""
    series = []
    for pid in range(1, 6):
        series += _generar_series(pid, n_dias=20, unidades=8.0)
    productos = [
        {"producto_id": pid, "nombre": f"P{pid}", "existencia": 40.0,
         "minimo": 10.0, "precio": 25}
        for pid in range(1, 6)
    ]
    return series, productos


def test_genera_recomendaciones_inventario(mock_db):
    series, productos = _datos_comedor()
    mock_db._q = {
        feat._SQL_VENTAS_PRODUCTO: series,
        "FROM producto": productos,
    }
    r = reco.generar_recomendaciones(1, dias=7)
    assert r["disponible"] is True
    tipos = [x["tipo"] for x in r["recomendaciones"]]
    assert "inventario" in tipos
    # Los 5 productos tienen riesgo ALTO -> prioridad ALTA ordenada arriba.
    inventario = [x for x in r["recomendaciones"] if x["tipo"] == "inventario"]
    assert len(inventario) == 5
    assert all(x["prioridad"] == "ALTA" for x in inventario)


def test_recomendacion_tiene_estructura_completa(mock_db):
    series, productos = _datos_comedor()
    mock_db._q = {
        feat._SQL_VENTAS_PRODUCTO: series,
        "FROM producto": productos,
    }
    r = reco.generar_recomendaciones(1, dias=7)
    for x in r["recomendaciones"]:
        assert x["tipo"]
        assert x["prioridad"]
        assert x["titulo"]
        assert x["explicacion"]
        assert x["accion_sugerida"]
        assert x["origen"]


def test_recomendacion_financiera_no_usa_ganancia(monkeypatch, mock_db):
    series, productos = _datos_comedor()
    mock_db._q = {
        feat._SQL_VENTAS_PRODUCTO: series,
        "FROM producto": productos,
    }
    mock_db._q1 = {
        "FROM detalle_venta dv "
        "JOIN transaccion t ON t.id = dv.transaccion_id": {"total": 1000},
        "SUM(monto)": {"total": 900},
        # conteo de operaciones y productos
        "COUNT(*) AS n FROM transaccion": {"n": 30},
        "COUNT(*) AS n FROM producto": {"n": 5},
    }
    fin = reco._recomendaciones_finanzas(1)
    assert len(fin) == 1
    texto = fin[0]["titulo"] + " " + fin[0]["explicacion"]
    assert "ganancia" not in texto.lower()


def test_recomendaciones_ordenan_por_prioridad(mock_db):
    series, productos = _datos_comedor()
    mock_db._q = {
        feat._SQL_VENTAS_PRODUCTO: series,
        "FROM producto": productos,
    }
    mock_db._q1 = {
        "FROM detalle_venta dv "
        "JOIN transaccion t ON t.id = dv.transaccion_id": {"total": 1000},
        "SUM(monto)": {"total": 900},
        "COUNT(*) AS n FROM transaccion": {"n": 30},
        "COUNT(*) AS n FROM producto": {"n": 5},
    }
    r = reco.generar_recomendaciones(1, dias=7)
    prioridades = [x["prioridad"] for x in r["recomendaciones"]]
    assert prioridades == sorted(prioridades,
                                 key=lambda p: {"ALTA": 0, "MEDIA": 1, "BAJA": 2}[p])


def test_registrar_recomendaciones(mock_db):
    resultado = {
        "disponible": True,
        "negocio_id": 1,
        "fecha_generacion": "2026-09-04",
        "periodo_dias": 7,
        "mensaje": "ok",
        "recomendaciones": [
            {"tipo": "inventario", "prioridad": "ALTA", "titulo": "t",
             "explicacion": "e", "accion_sugerida": "a", "origen": "inventario"}
        ],
    }
    n = reco.registrar_recomendaciones(1, resultado, dias=7)
    assert n == 1
    assert len(mock_db.executado) == 2  # DELETE + INSERT
    assert "INSERT INTO insight_ia" in mock_db.executado[1]


def test_registrar_recomendaciones_vacias(mock_db):
    resultado = {
        "disponible": True,
        "negocio_id": 1,
        "recomendaciones": [],
        "mensaje": "ok",
    }
    n = reco.registrar_recomendaciones(1, resultado, dias=7)
    assert n == 0
    assert mock_db.executado == []


def test_resumen_recomendaciones(monkeypatch, mock_db):
    # Simular que generar_recomendaciones devuelve algo previsible.
    import ml.recommendations as rec
    def fake_gen(nid, dias=7):
        return {
            "disponible": True,
            "recomendaciones": [
                {"prioridad": "ALTA", "titulo": "Inventario", "tipo": "inventario"},
                {"prioridad": "MEDIA", "titulo": "Ventas", "tipo": "ventas"},
            ],
        }
    monkeypatch.setattr(rec, "generar_recomendaciones", fake_gen)
    resumen = reco.resumen_recomendaciones(1, dias=7)
    assert len(resumen) == 2
    assert resumen[0]["prioridad"] == "ALTA"


def test_sin_datos_no_genera_recomendaciones_inventario(mock_db):
    # Negocio sin ventas ni productos desactualizados: no inventario en riesgo.
    mock_db._q = {"FROM producto": []}
    inv = reco._recomendaciones_inventario(
        {"productos": []}, dias=7)
    assert inv == []