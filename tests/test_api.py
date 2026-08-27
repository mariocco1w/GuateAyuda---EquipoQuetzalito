"""Tests de la API (Flask) con cliente de test y db mockeada.

Verifica que el backend responda correctamente (endpoints, Chat IA y
confirmación de operaciones) sin depender de PostgreSQL ni del esquema.
"""

import pytest

import app as app_module
import analytics.engine
import service


class MockAPI:
    def __init__(self):
        self.query_one_calls = []

    def query_one(self, sql, params=None):
        if "FROM negocio" in sql:
            return {"id": 1}
        return None

    def query(self, sql, params=None):
        return []

    def execute(self, sql, params=None):
        return 1


@pytest.fixture
def client(monkeypatch):
    mock = MockAPI()
    monkeypatch.setattr(app_module, "db", mock)
    monkeypatch.setattr(app_module, "service", service)
    monkeypatch.setattr(analytics.engine, "db", mock)
    monkeypatch.setattr(service, "db", mock)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.get_json()
    assert data["api"] == "GuateAyuda Backend"
    assert data["motor"]["capa_c_ml"] is False


def test_chat_venta(client):
    r = client.post("/api/negocio/1/chat", json={"mensaje": "Vendí 8 almuerzos a Q25"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["interpretado"] is True
    assert data["tipo"] == "venta"
    assert data["operacion"]["cantidad"] == 8
    assert data["operacion"]["precio_unitario"] == 25
    assert data["token_sesion"]


def test_chat_gasto(client):
    r = client.post("/api/negocio/1/chat", json={"mensaje": "Gasté Q150 comprando verduras"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["interpretado"] is True
    assert data["tipo"] == "gasto"
    assert data["operacion"]["monto"] == 150


def test_chat_no_interpreta(client):
    r = client.post("/api/negocio/1/chat", json={"mensaje": "hola que tal"})
    assert r.status_code == 422
    assert r.get_json()["interpretado"] is False


def test_chat_sin_mensaje(client):
    r = client.post("/api/negocio/1/chat", json={})
    assert r.status_code == 400


def test_operacion_confirmada_requiere_token(client, monkeypatch):
    r = client.post("/api/negocio/1/operacion", json={"mensaje_humano": "x"})
    assert r.status_code == 400
    assert "token" in r.get_json()["mensaje"].lower()


def test_operacion_con_token_invalido(client):
    r = client.post("/api/negocio/1/operacion",
                    json={"token_sesion": "invalido", "mensaje_humano": "x"})
    assert r.status_code == 422
