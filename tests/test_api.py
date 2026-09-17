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
        if "FROM producto" in sql:
            return [
                {"nombre": "café", "precio": 12, "existencia": 40, "minimo": 5, "activo": 1},
                {"nombre": "almuerzo", "precio": 25, "existencia": 3, "minimo": 4, "activo": 1},
            ]
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
    r = client.get("/api")
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
    # Pregunta desconocida: respaldo amigable (200) con sugerencias, sin 422.
    r = client.post("/api/negocio/1/chat", json={"mensaje": "hola que tal"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["interpretado"] is False
    assert data["consulta"] is False
    assert data["tipo"] == "fallback"
    assert "Aún no entiendo" in data["mensaje"]


def test_chat_operacion_incompleta_da_sugerencia(client):
    # Operación incompleta: 200 con los errores de validación.
    r = client.post("/api/negocio/1/chat", json={"mensaje": "Vendí almuerzos"})
    data = r.get_json()
    assert r.status_code == 200
    assert data["interpretado"] is False
    assert data["tipo"] == "fallback"
    assert "Faltan datos" in data["mensaje"]


def test_chat_consulta_asesor(client):
    r = client.post("/api/negocio/1/chat", json={"mensaje": "¿Quién eres?"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "asesor"
    assert "asesor virtual" in data["mensaje"].lower()


def test_chat_consulta_productos(client):
    r = client.post("/api/negocio/1/chat", json={"mensaje": "¿Qué productos tengo?"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "productos"
    assert len(data["datos"]) == 2
    assert data["datos"][0]["producto"] == "café"


def test_chat_consulta_saludo(client):
    r = client.post("/api/negocio/1/chat", json={"mensaje": "Hola"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "saludo"


def test_chat_consulta_ventas(client):
    r = client.post("/api/negocio/1/chat", json={"mensaje": "¿Cómo van mis ventas?"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "ventas"


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


# ---------------------------------------------------------------------------
# Centro de Inteligencia (FASE 6)
# ---------------------------------------------------------------------------

def test_prediccion_ventas(client, monkeypatch):
    def fake(negocio_id, dias):
        return {
            "disponible": True,
            "estado": "modelo_ml",
            "negocio_id": negocio_id,
            "periodo_dias": dias,
            "predicciones": [{"dia": "2026-09-05", "estimado": 100.0}],
            "por_producto": [],
            "mensaje": "Predicción (estimación, no certeza).",
        }
    monkeypatch.setattr(app_module, "pronostico_negocio", fake)
    r = client.get("/api/negocio/1/prediccion?dias=7")
    assert r.status_code == 200
    data = r.get_json()
    assert data["disponible"] is True
    assert data["periodo_dias"] == 7
    assert data["predicciones"][0]["estimado"] == 100.0


def test_inventario_predictivo(client, monkeypatch):
    def fake(negocio_id, dias):
        return {
            "disponible": True,
            "negocio_id": negocio_id,
            "periodo_dias": dias,
            "productos": [],
            "en_riesgo": [],
            "sin_datos": [],
            "mensaje": "ok",
        }
    monkeypatch.setattr(app_module, "analisis_inventario", fake)
    r = client.get("/api/negocio/1/inventario-predictivo?dias=7")
    assert r.status_code == 200
    data = r.get_json()
    assert data["disponible"] is True
    assert data["periodo_dias"] == 7


def test_anomalias(client, monkeypatch):
    def fake(negocio_id, dias):
        return {
            "disponible": False,
            "negocio_id": negocio_id,
            "periodo_dias": dias,
            "areas": {},
            "total_anomalias": 0,
            "mensaje": "Sin comportamientos inusuales en el periodo revisado.",
        }
    monkeypatch.setattr(app_module, "detectar_anomalias", fake)
    r = client.get("/api/negocio/1/anomalias?dias=30")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_anomalias"] == 0
    assert not data["disponible"]


def test_recomendaciones_y_persistencia(client, monkeypatch):
    llamadas = []

    def fake_gen(negocio_id, dias):
        return {
            "disponible": True,
            "negocio_id": negocio_id,
            "periodo_dias": dias,
            "recomendaciones": [{
                "tipo": "inventario", "prioridad": "ALTA", "titulo": "Riesgo",
                "explicacion": "e", "accion_sugerida": "a", "origen": "inventario",
            }],
            "total": 1,
            "mensaje": "ok",
        }

    def fake_reg(negocio_id, resultado, dias):
        llamadas.append((negocio_id, resultado, dias))
        return len(resultado.get("recomendaciones", []))

    monkeypatch.setattr(app_module, "generar_recomendaciones", fake_gen)
    monkeypatch.setattr(app_module, "registrar_recomendaciones", fake_reg)
    r = client.get("/api/negocio/1/recomendaciones?dias=7")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert data["guardadas_en_insight"] == 1
    assert llamadas[0][0] == 1


def test_recomendaciones_sin_persistencia_no_rompe(client, monkeypatch):
    def fake_gen(negocio_id, dias):
        return {
            "disponible": True,
            "negocio_id": negocio_id,
            "recomendaciones": [],
            "total": 0,
            "mensaje": "ok",
        }

    def fake_reg(negocio_id, resultado, dias):
        raise RuntimeError("base de datos no disponible")

    monkeypatch.setattr(app_module, "generar_recomendaciones", fake_gen)
    monkeypatch.setattr(app_module, "registrar_recomendaciones", fake_reg)
    r = client.get("/api/negocio/1/recomendaciones?dias=7")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 0
    assert data["guardadas_en_insight"] == 0


def test_prediccion_negocio_no_existe(client, monkeypatch):
    monkeypatch.setattr(app_module, "negocio_existe", lambda nid: None)
    r = client.get("/api/negocio/999/prediccion")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# FASE 7: chat conectado al centro de inteligencia
# ---------------------------------------------------------------------------

def test_chat_prediccion(client, monkeypatch):
    def fake(nid, dias):
        return {
            "disponible": True, "estado": "modelo_ml", "periodo_dias": dias,
            "predicciones": [{"dia": "2026-09-05", "estimado": 100.0}],
            "por_producto": [], "mensaje": "ok",
        }
    monkeypatch.setattr(app_module, "pronostico_negocio", fake)
    r = client.post("/api/negocio/1/chat",
                    json={"mensaje": "Predice mis ventas"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "prediccion"
    assert "estimación" in data["mensaje"].lower() or "estiman" in data["mensaje"].lower()


def test_chat_prediccion_sin_datos(client, monkeypatch):
    def fake(nid, dias):
        return {"disponible": False, "mensaje": "No hay datos suficientes."}
    monkeypatch.setattr(app_module, "pronostico_negocio", fake)
    r = client.post("/api/negocio/1/chat",
                    json={"mensaje": "¿Cuánto crees que venderé?"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "prediccion"
    assert "No hay" in data["mensaje"]


def test_chat_inventario_riesgo(client, monkeypatch):
    def fake(nid, dias):
        return {
            "disponible": True, "en_riesgo": [
                {"producto": "Almuerzo", "dias_hasta_agotamiento": 3.0,
                 "riesgo": "ALTO", "reposicion_sugerida": 20},
            ],
            "productos": [], "sin_datos": [], "mensaje": "ok",
        }
    monkeypatch.setattr(app_module, "analisis_inventario", fake)
    r = client.post("/api/negocio/1/chat",
                    json={"mensaje": "¿Qué productos se van a agotar?"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "inventario_riesgo"
    assert data["datos"][0]["etiqueta"] == "Almuerzo"


def test_chat_inventario_riesgo_sin_riesgo(client, monkeypatch):
    monkeypatch.setattr(app_module, "analisis_inventario",
                        lambda nid, dias: {"en_riesgo": [], "disponible": True})
    r = client.post("/api/negocio/1/chat",
                    json={"mensaje": "¿Qué productos están en riesgo?"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "inventario_riesgo"
    assert "no se detectaron" in data["mensaje"].lower()


def test_chat_anomalias(client, monkeypatch):
    def fake(nid, dias):
        return {
            "disponible": True, "total_anomalias": 1,
            "areas": {"ventas": {"anomalias": [{
                "fecha": "2026-08-22", "desviacion_porcentual": 31.0,
                "direccion": "alta", "requiere_revision": True,
            }]}},
            "mensaje": "ok",
        }
    monkeypatch.setattr(app_module, "detectar_anomalias", fake)
    r = client.post("/api/negocio/1/chat",
                    json={"mensaje": "¿Detectaste algo extraño?"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "anomalias"
    assert "requieren revisión" in data["mensaje"].lower()


def test_chat_anomalias_sin_hallazgos(client, monkeypatch):
    monkeypatch.setattr(app_module, "detectar_anomalias",
                        lambda nid, dias: {"disponible": False,
                                           "total_anomalias": 0,
                                           "areas": {}})
    r = client.post("/api/negocio/1/chat", json={"mensaje": "¿Hay anomalías?"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "anomalias"
    assert "no se detectaron" in data["mensaje"].lower()


def test_chat_recomendaciones(client, monkeypatch):
    def fake(nid, dias):
        return {
            "disponible": True,
            "recomendaciones": [{
                "tipo": "inventario", "prioridad": "ALTA", "titulo": "Riesgo",
                "explicacion": "e", "accion_sugerida": "Revisa inventario.",
                "origen": "inventario",
            }],
            "total": 1, "mensaje": "ok",
        }
    monkeypatch.setattr(app_module, "generar_recomendaciones", fake)
    r = client.post("/api/negocio/1/chat",
                    json={"mensaje": "¿Qué me recomiendas?"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "recomendaciones"
    assert data["datos"][0]["valor"].startswith("[ALTA]")


def test_chat_recomendaciones_vacias(client, monkeypatch):
    monkeypatch.setattr(app_module, "generar_recomendaciones",
                        lambda nid, dias: {"recomendaciones": [], "total": 0})
    r = client.post("/api/negocio/1/chat", json={"mensaje": "¿Qué me sugieres?"})
    data = r.get_json()
    assert data["consulta"] is True
    assert data["tipo"] == "recomendaciones"
