"""Testcases completos del sistema GuateAyuda.

Cubre:
1. Esquema SQL y base de datos (tablas, fallback SQLite, inicialización).
2. Renderizado del Frontend (GET / sirve index.html con las secciones de Dashboard y Chat IA).
3. Endpoints API del backend (/api/negocios, /api/negocio/<id>/dashboard, etc.).
4. Flujo End-to-End (E2E): Chat IA -> Interpretación -> Token -> Confirmación -> Actualización Dashboard.
"""

import pytest
import app as app_module
import db
import service
import analytics.engine


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    # Inicializar la DB de respaldo para pruebas
    db.init_sqlite_db(clear=True)
    # Insertar un negocio de prueba
    db.execute(
        "INSERT INTO negocio (id, nombre, propietario, actividad_principal, departamento, municipio) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, "Comedor Doña María (DEMO)", "María Xitumul", "Venta de alimentos", "Guatemala", "Guatemala")
    )
    return app_module.app.test_client()


def test_sql_schema_and_tables():
    """Verifica que las tablas del esquema guateayuda existan en la base de datos."""
    db.init_sqlite_db(clear=True)
    conn = db.get_sqlite_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tablas = [row[0] for row in cur.fetchall()]
        assert "negocio" in tablas
        assert "producto" in tablas
        assert "transaccion" in tablas
        assert "detalle_venta" in tablas
        assert "interaccion" in tablas
        assert "sesion_conversacional" in tablas
    finally:
        conn.close()


def test_frontend_rendering_root(client):
    """Verifica que GET / renderice correctamente el index.html del Frontend con el Dashboard y Chat IA."""
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "GuateAyuda" in html
    assert "Dashboard" in html
    assert "Chat IA" in html
    assert "Comedor Doña María" in html


def test_api_endpoints_negocios(client):
    """Verifica el endpoint GET /api/negocios y GET /api/negocio/1."""
    r = client.get("/api/negocios")
    assert r.status_code == 200
    data = r.get_json()
    assert "negocios" in data
    assert len(data["negocios"]) >= 1
    assert data["negocios"][0]["nombre"] == "Comedor Doña María (DEMO)"

    r2 = client.get("/api/negocio/1")
    assert r2.status_code == 200
    assert r2.get_json()["id"] == 1


def test_api_dashboard(client):
    """Verifica el motor analítico y el endpoint de dashboard."""
    r = client.get("/api/negocio/1/dashboard")
    assert r.status_code == 200
    data = r.get_json()
    assert "ventas_registradas" in data
    assert "gastos_registrados" in data
    assert "numero_operaciones" in data
    assert "productos_activos" in data


def test_e2e_chat_and_confirmation_flow(client):
    """Flujo E2E completo:
    1. Usuario envía mensaje al Chat IA: "Vendí 10 almuerzos a Q25".
    2. El sistema interpreta la venta y devuelve un token_sesion.
    3. Usuario confirma la operación con el token_sesion.
    4. Se verifica que la transacción se guarde y el dashboard se actualice con Q250.
    """
    # 1. Enviar mensaje al chat
    r_chat = client.post("/api/negocio/1/chat", json={"mensaje": "Vendí 10 almuerzos a Q25"})
    assert r_chat.status_code == 200
    chat_data = r_chat.get_json()
    assert chat_data["interpretado"] is True
    assert chat_data["tipo"] == "venta"
    assert chat_data["operacion"]["cantidad"] == 10
    assert chat_data["operacion"]["precio_unitario"] == 25
    token = chat_data["token_sesion"]
    assert token

    # 2. Confirmar la operación
    r_op = client.post("/api/negocio/1/operacion", json={
        "token_sesion": token,
        "mensaje_humano": "Vendí 10 almuerzos a Q25"
    })
    assert r_op.status_code == 200
    op_data = r_op.get_json()
    assert op_data["guardado"] is True
    assert op_data["resultado"]["total"] == 250.0

    # 3. Verificar que el Dashboard refleje la venta de Q250
    r_dash = client.get("/api/negocio/1/dashboard")
    assert r_dash.status_code == 200
    dash_data = r_dash.get_json()
    assert dash_data["ventas_registradas"] == 250.0
    assert dash_data["numero_operaciones"] == 1
