"""Capa de conexión a PostgreSQL para GuateAyuda con fallback SQLite transparente.

Este módulo maneja la CONEXIÓN a la base de datos PostgreSQL (esquema `guateayuda`)
definido en `bd/schema.sql`. Si PostgreSQL no está disponible localmente,
utiliza automáticamente SQLite con el mismo esquema para permitir el desarrollo
y ejecución inmediata sin depender de PostgreSQL.
"""

import os
import re
import sqlite3
from pathlib import Path

import psycopg2
import psycopg2.extras

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "bd" / "schema.sql"
SQLITE_DB_PATH = BASE_DIR / "guateayuda.db"

_USE_SQLITE = False


def config():
    """Devuelve el diccionario de configuración de conexión a PostgreSQL."""
    return {
        "host": os.getenv("GUATEAYUDA_HOST", "localhost"),
        "port": os.getenv("GUATEAYUDA_PORT", "5432"),
        "dbname": os.getenv("GUATEAYUDA_DB", "guateayuda"),
        "user": os.getenv("GUATEAYUDA_USER", "postgres"),
        "password": os.getenv("GUATEAYUDA_PASSWORD", ""),
        "connect_timeout": 2,
        "options": "-c search_path=guateayuda,public",
    }


def get_sqlite_conn():
    """Abre y devuelve una conexión a la base SQLite de respaldo."""
    conn = sqlite3.connect(str(SQLITE_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_conn():
    """Abre y devuelve una conexión nueva a PostgreSQL o SQLite."""
    global _USE_SQLITE
    if _USE_SQLITE:
        return get_sqlite_conn()

    try:
        return psycopg2.connect(**config())
    except Exception:
        _USE_SQLITE = True
        init_sqlite_db()
        return get_sqlite_conn()


def _convert_sql_for_sqlite(sql):
    """Convierte consultas sintácticamente compatibles de PostgreSQL a SQLite."""
    # Quitar prefijo guateayuda.
    sql = re.sub(r"\bguateayuda\.", "", sql)
    # Reemplazar %s con ?
    sql = sql.replace("%s", "?")
    # Convertir t.fecha::date a DATE(t.fecha)
    sql = re.sub(r"(\w+(?:\.\w+)?)::date", r"DATE(\1)", sql)
    # Reemplazar GREATEST con MAX o CASE en update
    if "GREATEST(" in sql:
        sql = re.sub(
            r"GREATEST\s*\(\s*COALESCE\s*\(\s*existencia\s*,\s*0\s*\)\s*-\s*\?,\s*0\s*\)",
            "MAX(COALESCE(existencia,0) - ?, 0)",
            sql,
            flags=re.IGNORECASE,
        )
    return sql


def query(sql, params=None):
    """Ejecuta un SELECT y devuelve la lista de filas como diccionarios."""
    conn = get_conn()
    try:
        if _USE_SQLITE or isinstance(conn, sqlite3.Connection):
            sql_sqlite = _convert_sql_for_sqlite(sql)
            cur = conn.cursor()
            cur.execute(sql_sqlite, params or ())
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        else:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def query_one(sql, params=None):
    """Ejecuta un SELECT y devuelve la primera fila (o None)."""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None):
    """Ejecuta una sentencia INSERT/UPDATE/DELETE y devuelve el rowcount."""
    conn = get_conn()
    try:
        if _USE_SQLITE or isinstance(conn, sqlite3.Connection):
            sql_sqlite = _convert_sql_for_sqlite(sql)
            cur = conn.cursor()
            cur.execute(sql_sqlite, params or ())
            conn.commit()
            return cur.rowcount
        else:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                conn.commit()
                return cur.rowcount
    except Exception:
        conn.rollback() if hasattr(conn, "rollback") else None
        raise
    finally:
        conn.close()


def execute_many(sql, seq_of_params):
    """Ejecuta la misma sentencia para varias tuplas de parámetros."""
    conn = get_conn()
    try:
        if _USE_SQLITE or isinstance(conn, sqlite3.Connection):
            sql_sqlite = _convert_sql_for_sqlite(sql)
            cur = conn.cursor()
            cur.executemany(sql_sqlite, seq_of_params)
            conn.commit()
            return cur.rowcount
        else:
            with conn.cursor() as cur:
                cur.executemany(sql, seq_of_params)
                conn.commit()
                return cur.rowcount
    except Exception:
        conn.rollback() if hasattr(conn, "rollback") else None
        raise
    finally:
        conn.close()


def init_sqlite_db(clear=False):
    """Inicializa la estructura SQLite coincidente con bd/schema.sql."""
    conn = sqlite3.connect(str(SQLITE_DB_PATH))
    try:
        cur = conn.cursor()
        if clear:
            cur.executescript("""
                DROP TABLE IF EXISTS detalle_venta;
                DROP TABLE IF EXISTS movimiento_inventario;
                DROP TABLE IF EXISTS transaccion;
                DROP TABLE IF EXISTS interaccion;
                DROP TABLE IF EXISTS sesion_conversacional;
                DROP TABLE IF EXISTS producto;
                DROP TABLE IF EXISTS hecho_negocio;
                DROP TABLE IF EXISTS insight_ia;
                DROP TABLE IF EXISTS negocio;
            """)
        
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS negocio (
                id INTEGER PRIMARY KEY,
                nombre TEXT NOT NULL,
                propietario TEXT,
                actividad_principal TEXT,
                actividad TEXT,
                descripcion TEXT,
                departamento TEXT,
                municipio TEXT,
                ubicacion TEXT,
                atributos TEXT DEFAULT '{}',
                activo INTEGER DEFAULT 1,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sesion_conversacional (
                id TEXT PRIMARY KEY,
                negocio_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                expira_en TEXT NOT NULL,
                ultima_actividad TEXT,
                revocado_en TEXT
            );

            CREATE TABLE IF NOT EXISTS interaccion (
                id INTEGER PRIMARY KEY,
                negocio_id INTEGER NOT NULL,
                sesion_id TEXT,
                mensaje_original TEXT NOT NULL,
                intent TEXT,
                tipo_detectado TEXT,
                modelo TEXT,
                version_modelo TEXT,
                version_prompt TEXT,
                confidence REAL,
                estructura TEXT,
                datos_extraidos TEXT,
                estructura_corregida TEXT,
                estado TEXT DEFAULT 'PENDIENTE',
                confirmado INTEGER DEFAULT 0,
                resultado_persistencia TEXT,
                latencia_ms INTEGER,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                confirmado_en TEXT
            );

            CREATE TABLE IF NOT EXISTS producto (
                id INTEGER PRIMARY KEY,
                negocio_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                tipo_item TEXT DEFAULT 'PRODUCTO',
                unidad_medida TEXT,
                precio_referencia REAL,
                precio REAL,
                costo_referencia REAL,
                maneja_inventario INTEGER DEFAULT 1,
                existencia REAL DEFAULT 0,
                inventario_minimo REAL DEFAULT 0,
                minimo REAL DEFAULT 0,
                atributos TEXT DEFAULT '{}',
                activo INTEGER DEFAULT 1,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transaccion (
                id INTEGER PRIMARY KEY,
                negocio_id INTEGER NOT NULL,
                interaccion_id INTEGER,
                tipo TEXT NOT NULL,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                descripcion TEXT,
                monto REAL NOT NULL,
                moneda TEXT DEFAULT 'GTQ',
                origen TEXT DEFAULT 'WEB',
                estado TEXT DEFAULT 'CONFIRMADA',
                atributos TEXT DEFAULT '{}',
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS detalle_venta (
                id INTEGER PRIMARY KEY,
                negocio_id INTEGER NOT NULL,
                transaccion_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                cantidad REAL NOT NULL,
                precio_unitario REAL NOT NULL,
                subtotal REAL NOT NULL,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS movimiento_inventario (
                id INTEGER PRIMARY KEY,
                negocio_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                transaccion_id INTEGER,
                interaccion_id INTEGER,
                tipo TEXT NOT NULL,
                cantidad_delta REAL NOT NULL,
                existencia_anterior REAL,
                existencia_posterior REAL,
                descripcion TEXT,
                atributos TEXT DEFAULT '{}',
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS hecho_negocio (
                id INTEGER PRIMARY KEY,
                negocio_id INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                clave TEXT NOT NULL,
                valor TEXT NOT NULL,
                fuente TEXT NOT NULL,
                confidence REAL,
                confirmado_usuario INTEGER DEFAULT 0,
                vigente INTEGER DEFAULT 1,
                vigente_desde TEXT DEFAULT CURRENT_TIMESTAMP,
                vigente_hasta TEXT,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS insight_ia (
                id INTEGER PRIMARY KEY,
                negocio_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                evidencia TEXT DEFAULT '{}',
                confidence REAL,
                modelo TEXT,
                version_modelo TEXT,
                version_prompt TEXT,
                estado TEXT DEFAULT 'ACTIVO',
                generado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                expira_en TEXT
            );
        """)
        conn.commit()
    finally:
        conn.close()


def init_db(clear=False):
    """Ejecuta el esquema SQL definido por el equipo (bd/schema.sql) o SQLite."""
    global _USE_SQLITE
    try:
        conn = psycopg2.connect(**config())
        try:
            with conn.cursor() as cur:
                if clear:
                    cur.execute("DROP SCHEMA IF EXISTS guateayuda CASCADE;")
                if SCHEMA_PATH.exists():
                    cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
                    conn.commit()
        finally:
            conn.close()
    except Exception:
        _USE_SQLITE = True
        init_sqlite_db(clear=clear)

