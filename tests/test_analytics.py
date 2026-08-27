"""Tests del motor analítico y de la capa de servicio con datos en memoria.

Se usan mocks de `db` para verificar la lógica sin depender de PostgreSQL
ni del esquema (que aún no está listo). Cubre el control del backend:
cálculos correctos, reglas del proyecto y gestión de confirmación.
"""

import pytest

import analytics.engine
import service
from analytics import (
    indicadores_principales,
    tendencia_ventas,
)

# ---------------------------------------------------------------------------
# Mocks de la capa db
# ---------------------------------------------------------------------------

class MockDB:
    """Simula db.query_one / db.query / db.execute con datos fijos."""

    def __init__(self, query_one_map=None, query_map=None):
        self._q1 = query_one_map or {}
        self._q = query_map or {}
        self.executado = []

    def query_one(self, sql, params=None):
        for clave, valor in self._q1.items():
            if clave in sql:
                return valor
        return None

    def query(self, sql, params=None):
        for clave, valor in self._q.items():
            if clave in sql:
                return valor
        return []

    def execute(self, sql, params=None):
        self.executado.append(sql)
        return 1


@pytest.fixture
def mock_db(monkeypatch):
    md = MockDB(query_one_map={
        "SUM(dv.subtotal)": {"total": 1250},
        "SUM(monto)": {"total": 300},
        "COUNT(*)": {"n": 40},
        "COALESCE(MAX(id)": {"max_id": 5},
    })
    monkeypatch.setattr(analytics.engine, "db", md)
    monkeypatch.setattr(service, "db", md)
    return md


def test_indicadores_principales(mock_db):
    ind = indicadores_principales(1)
    assert ind["ventas_registradas"] == 1250.0
    assert ind["gastos_registrados"] == 300.0
    assert ind["numero_operaciones"] == 40


def test_indicadores_no_llaman_ganancia(mock_db):
    ind = indicadores_principales(1)
    # El MVP no expone "ganancia" (ventas - gastos) - sección 9.
    assert "ganancia" not in ind


def test_tendencia_sin_suficiente_historial(monkeypatch, mock_db):
    mock_db._q["GROUP BY t.fecha::date"] = [{"dia": "1", "total": 100}]
    res = tendencia_ventas(1)
    assert res["disponible"] is False


# ---------------------------------------------------------------------------
# Cálculo de totales en la capa de servicio (sección 12: los hace Python)
# ---------------------------------------------------------------------------

def test_service_venta_calcula_total_en_python(mock_db):
    # El backend (no el intérprete) calcula el subtotal: 8 x 25 = 200.
    op = {"tipo": "venta", "producto": "almuerzo",
          "cantidad": 8, "precio_unitario": 25}
    resultado = service.guardar_venta(1, op)
    assert resultado["total"] == 200
    # Verificar que hubo escritura (inserts de transacción/detalle/inventario).
    assert mock_db.executado


def test_service_venta_valida_datos_invalidos(mock_db):
    with pytest.raises(ValueError):
        service.guardar_venta(1, {"tipo": "venta", "producto": "", "cantidad": 0, "precio_unitario": 0})


def test_service_gasto_valida_monto(mock_db):
    with pytest.raises(ValueError):
        service.guardar_gasto(1, {"tipo": "gasto", "monto": 0})


def test_sesion_y_tokens():
    t1 = service.nueva_sesion({"tipo": "venta", "producto": "x"})
    t2 = service.nueva_sesion({"tipo": "gasto", "concepto": "y"})
    assert t1 != t2
    assert service.obtener_sesion(t1)["tipo"] == "venta"
    assert service.obtener_sesion(t2)["tipo"] == "gasto"
    service.eliminar_sesion(t1)
    assert service.obtener_sesion(t1) is None


def test_guardar_sesion_invalida(mock_db):
    with pytest.raises(ValueError):
        service.guardar_operacion_confirmada(1, "token-inexistente")
