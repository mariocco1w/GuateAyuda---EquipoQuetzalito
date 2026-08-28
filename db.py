"""Capa de conexión a PostgreSQL para GuateAyuda.

Este módulo solo maneja la CONEXIÓN a la base de datos. El esquema SQL
(creación de tablas) vive en `bd/schema.sql` y lo mantiene otro compañero.

Configuración vía variables de entorno con valores por defecto:

    GUATEAYUDA_HOST     (default: localhost)
    GUATEAYUDA_PORT     (default: 5432)
    GUATEAYUDA_DB       (default: guateayuda)
    GUATEAYUDA_USER     (default: postgres)
    GUATEAYUDA_PASSWORD (default: vacío)
"""

import os
from pathlib import Path

import psycopg2
import psycopg2.extras

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "bd" / "schema.sql"


def config():
    """Devuelve el diccionario de configuración de conexión."""
    return {
        "host": os.getenv("GUATEAYUDA_HOST", "localhost"),
        "port": os.getenv("GUATEAYUDA_PORT", "5432"),
        "dbname": os.getenv("GUATEAYUDA_DB", "guateayuda"),
        "user": os.getenv("GUATEAYUDA_USER", "postgres"),
        "password": os.getenv("GUATEAYUDA_PASSWORD", ""),
    }


def get_conn():
    """Abre y devuelve una conexión nueva a PostgreSQL."""
    return psycopg2.connect(**config())


def query(sql, params=None):
    """Ejecuta un SELECT y devuelve la lista de filas como diccionarios."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
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
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_many(sql, seq_of_params):
    """Ejecuta la misma sentencia para varias tuplas de parámetros."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, seq_of_params)
            conn.commit()
            return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(clear=False):
    """Ejecuta el esquema SQL definido por el equipo (bd/schema.sql).

    Args:
        clear (bool): si True, borra las tablas demo antes de recrear el esquema.
    """
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró el esquema en {SCHEMA_PATH}. "
            "El compañero encargado de `bd` debe crearlo."
        )

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if clear:
                cur.execute(
                    """
                    DROP TABLE IF EXISTS detalle_venta, interaccion,
                        transaccion, producto, negocio CASCADE
                    """
                )
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
