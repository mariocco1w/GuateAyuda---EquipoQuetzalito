"""Tests de detección de anomalías (FASE 4).

Cubre:

    * Detección de picos/valores atípicos con z-score MAD.
    * Áreas sin datos suficientes (sin_datos).
    * Nunca afirma fraude o error: solo "requiere revisión".
    * Agregado de anomalías flagrantes.
"""

import pytest

import ml.anomaly as anom


class MockDB:
    """Simula db.query según subcadenas dentro del SQL."""

    def __init__(self, query_map=None):
        self._q = query_map or {}

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


def _serie_base(n=10, valor=100.0, atipico=None):
    filas = []
    inicio = "2026-08-01"
    from datetime import date, timedelta
    d = date.fromisoformat(inicio)
    for i in range(n):
        v = valor if atipico != i else atipico
        filas.append({
            "dia": (d + timedelta(days=i)).isoformat(),
            "total": v if v is not None else valor,
        })
    return filas


def _movimientos(n=10):
    return [
        {
            "dia": f"2026-08-{(i % 28) + 1:02d}",
            "producto": f"P{i % 2}",
            "salida": 10.0,
            "entrada": 0.0,
        }
        for i in range(n)
    ]


@pytest.fixture
def mock_db(monkeypatch):
    md = MockDB()
    monkeypatch.setattr(anom, "db", md)
    return md


def test_no_detecta_sin_variabilidad(mock_db):
    serie = _serie_base(valor=100.0)
    # Spin-off: reutiliza la lógica interna directamente.
    res = anom._mad_zscore([100.0] * 8)
    assert res == [0.0] * 8


def test_detecta_pico_atipico(mock_db):
    serie = _serie_base(n=10, valor=100.0)
    serie[5]["total"] = 500.0
    anomalias = anom._anomalias_de_serie("ventas", [
        {"fecha": f["dia"], "valor": f["total"], "contexto": None}
        for f in serie
    ])
    assert len(anomalias) >= 1
    a = anomalias[0]
    assert a["requiere_revision"] is True
    assert a["direccion"] == "alta"
    assert a["mediana"] == 100.0
    assert a["valor"] == 500.0


def test_mensaje_no_afirma_fraude():
    anomalias = anom._anomalias_de_serie("ventas", [
        {"fecha": "2026-08-01", "valor": 100.0, "contexto": None},
        {"fecha": "2026-08-02", "valor": 100.0, "contexto": None},
        {"fecha": "2026-08-03", "valor": 100.0, "contexto": None},
        {"fecha": "2026-08-04", "valor": 100.0, "contexto": None},
        {"fecha": "2026-08-05", "valor": 100.0, "contexto": None},
        {"fecha": "2026-08-06", "valor": 100.0, "contexto": None},
        {"fecha": "2026-08-07", "valor": 100.0, "contexto": None},
        {"fecha": "2026-08-08", "valor": 100.0, "contexto": None},
        {"fecha": "2026-08-09", "valor": 100.0, "contexto": None},
        {"fecha": "2026-08-10", "valor": 400.0, "contexto": None},
    ])
    for a in anomalias:
        assert "Requiere revisión" in a["mensaje"]
        # No debe decir fraude/error.
        assert "fraude" not in a["mensaje"].lower()
        assert "error" not in a["mensaje"].lower()


def test_sin_datos_por_area(mock_db):
    # Ninguna consulta devuelve filas -> todas sin datos.
    r = anom.detectar_anomalias(1, dias=30)
    assert r["disponible"] is False
    for area in ("ventas", "gastos", "compras", "inventario"):
        assert area in r["areas"]
        assert r["areas"][area]["disponible"] is False


def test_detecta_en_todas_las_areas(mock_db):
    base = _serie_base(n=10, valor=100.0)
    base[3]["total"] = 400.0
    regiones_ventas = [
        {"dia": f["dia"], "total": f["total"]} for f in base]

    mock_db._q = {
        anom._SQL_VENTAS_DIARIAS: regiones_ventas,
        anom._SQL_GASTOS_DIARIOS: regiones_ventas,
        anom._SQL_COMPRAS_DIARIAS: regiones_ventas,
        anom._SQL_MOVIMIENTOS: _movimientos(n=10),
    }
    r = anom.detectar_anomalias(1, dias=30)
    assert r["disponible"] is True
    assert r["areas"]["ventas"]["disponible"] is True
    assert len(r["areas"]["gastos"]["anomalias"]) >= 1


def test_anomalias_flagrantes_agrega_area(mock_db):
    base = _serie_base(n=10, valor=100.0)
    base[2]["total"] = 400.0
    mock_db._q = {
        anom._SQL_VENTAS_DIARIAS: [
            {"dia": f["dia"], "total": f["total"]} for f in base],
    }
    todas = anom.anomalias_flagrantes(1)
    assert len(todas) >= 1
    assert all(a.get("area") for a in todas)


def test_valores_insuficientes_por_dias(mock_db):
    # Solo 3 días -> no hay patrón detectable.
    base = _serie_base(n=3, valor=100.0)
    mock_db._q = {
        anom._SQL_VENTAS_DIARIAS: [
            {"dia": f["dia"], "total": f["total"]} for f in base],
    }
    r = anom.detectar_anomalias(1, dias=30)
    assert r["areas"]["ventas"]["disponible"] is False