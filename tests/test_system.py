"""Testcases ajustados al nuevo esquema de GuateAyuda (Sitio Público vs Plataforma Privada).

Cubre:
1. Esquema SQL y fallback SQLite.
2. Renderizado del Sitio Público (GET /).
3. Autenticación y Registro (Login/Logout/Register).
4. Acceso protegido a Dashboard, Chat y Reportes PDF.
5. Flujo E2E (Autenticado).
"""

import pytest
import app as app_module
import db
import service


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    app_module.app.config["SECRET_KEY"] = "testkey"
    # Inicializar la DB de respaldo para pruebas
    db.init_sqlite_db(clear=True)
    # Insertar un negocio de prueba
    db.execute(
        "INSERT INTO negocio (id, nombre, propietario, actividad_principal) "
        "VALUES (?, ?, ?, ?)",
        (1, "Comedor Doña María (DEMO)", "María Xitumul", "Venta de alimentos")
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


def test_public_site_rendering(client):
    """Verifica que el sitio público no requiera login."""
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "GuateAyuda" in html
    assert "Iniciar sesión" in html
    assert "Comenzar" in html


def test_auth_flow(client):
    """Verifica el flujo de login y logout."""
    # Login
    r = client.post("/login", data={"user": "test"}, follow_redirects=True)
    assert r.status_code == 200
    
    # Dashboard debería estar accesible
    r_dash = client.get("/dashboard")
    assert r_dash.status_code == 200
    
    # Logout
    r_out = client.get("/logout", follow_redirects=True)
    assert r_out.status_code == 200
    
    # Dashboard debería redirigir a login
    r_dash_protected = client.get("/dashboard")
    assert r_dash_protected.status_code == 302 # Redirect


def test_private_routes_protection(client):
    """Verifica que rutas privadas redirijan si no hay sesión."""
    for route in ["/dashboard", "/chat", "/reportes"]:
        r = client.get(route)
        assert r.status_code == 302 # Redirige al login


def test_report_generation(client):
    """Verifica que el reporte PDF se genere estando autenticado."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["negocio_id"] = 1
        
    r = client.get("/reportes")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/pdf"


def test_configuracion_route(client):
    """Verifica el acceso a la configuración de empresa."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["negocio_id"] = 1
    r = client.get("/empresa/configuracion")
    assert r.status_code == 200


