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
    """Verifica que el reporte PDF se genere estando autenticado y con contenido."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["negocio_id"] = 1

    # Sembrar un producto y una venta para que el reporte tenga datos reales.
    db.execute(
        "INSERT INTO producto (negocio_id, nombre, precio, existencia, minimo) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "café Cocina", 12, 40, 5),
    )
    p = db.query_one("SELECT id FROM producto WHERE negocio_id = 1 ORDER BY id DESC LIMIT 1")
    db.execute(
        "INSERT INTO transaccion (negocio_id, tipo, monto, estado, origen) "
        "VALUES (?, 'VENTA', 96, 'CONFIRMADA', 'WEB')",
        (1,),
    )
    t = db.query_one("SELECT id FROM transaccion WHERE negocio_id = 1 ORDER BY id DESC LIMIT 1")
    db.execute(
        "INSERT INTO detalle_venta "
        "(negocio_id, transaccion_id, producto_id, cantidad, precio_unitario, subtotal) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, t["id"], p["id"], 8, 12, 96),
    )

    r = client.get("/reportes")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/pdf"
    # El reporte ya no es un stub de 1 KB: debe superar un umbral razonable
    # y contener varias páginas (banda de encabezado + secciones + tabla).
    assert len(r.data) > 4096
    assert "/Type /Page" in r.data.decode("latin-1", "replace")


def test_configuracion_route(client):
    """Verifica el acceso a la configuración de empresa."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["negocio_id"] = 1
    r = client.get("/empresa/configuracion")
    assert r.status_code == 200


def test_guardar_compra_persistencia():
    """Verifica que guardar una compra crea/asocia producto, suma inventario
    y registra la transacción como COMPRA con el proveedor."""
    db.init_sqlite_db(clear=True)
    db.execute(
        "INSERT INTO negocio (id, nombre, propietario, actividad_principal) "
        "VALUES (?, ?, ?, ?)",
        (1, "Comedor Doña María (DEMO)", "María Xitumul", "Venta de alimentos"),
    )

    resultado = service.guardar_compra(1, {
        "producto": "tomates",
        "cantidad": 100,
        "precio_unitario": 5,
        "proveedor": "Don Pedro",
    })

    assert resultado["tipo"] == "compra"
    assert resultado["cantidad"] == 100

    # El producto se creó con inventario = 100
    p = db.query_one(
        "SELECT id, existencia FROM producto WHERE negocio_id = 1 AND LOWER(nombre) = 'tomates'"
    )
    assert p is not None
    assert p["existencia"] == 100

    # La transacción tiene tipo COMPRA y guarda el proveedor en atributos
    t = db.query_one(
        "SELECT tipo, atributos FROM transaccion WHERE negocio_id = 1 ORDER BY id DESC LIMIT 1"
    )
    assert t["tipo"] == "COMPRA"
    assert "Don Pedro" in str(t["atributos"])



