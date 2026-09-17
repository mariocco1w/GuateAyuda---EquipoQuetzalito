"""Vocabulario guatemalteco de productos para el intérprete de GuateAyuda.

Carga alias coloquiales, regionalismos y algunas formas mayas desde
`bd/vocabulario_productos_Guatemala.txt` y los asocia a un producto canónico.

Uso principal:
    canonicalizar_producto("guineos")  -> "banano"
    canonicalizar_producto("güisquiles") -> "guisquil"
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

VOCAB_PATH = Path(__file__).resolve().parent / "bd" / "vocabulario_productos_Guatemala.txt"

# Alias demasiado cortos o ambiguos (colisionan con español/otros productos).
ALIAS_EXCLUIDOS = {
    "is", "iis", "oj", "ooj", "ox", "oom", "ik", "iik", "och", "rum",
    "tul", "chin", "peer", "aj", "ajn", "lo", "se", "me", "mi", "un",
    "una", "el", "la", "de", "al", "en", "pata",  # pata = guayaba, muy ambiguo
    "frances",  # solo con "pan frances"
}

# Correcciones ortográficas frecuentes (sin acentos → forma canónica legible).
ORTOGRAFIA_COMUN = {
    "guisquil": "guisquil",
    "guisquiles": "guisquil",
    "guicoy": "guicoy",
    "guicoyes": "guicoy",
    "guicoyito": "guicoy",
    "guicoyitos": "guicoy",
    "pepian": "pepian",
    "jocon": "jocon",
    "maiz": "maiz",
    "limon": "limon",
    "limones": "limon",
    "platano": "platano",
    "platanos": "platano",
    "nispero": "nispero",
    "nisperos": "nispero",
    "brocoli": "brocoli",
    "camaron": "camaron",
    "camarones": "camaron",
    "jamon": "jamon",
    "jamones": "jamon",
    "chiletepes": "chiltepe",
}


def _sin_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _norm_clave(texto: str) -> str:
    """Clave de búsqueda: minúsculas, sin acentos, sin apóstrofos mayas raros."""
    t = _sin_acentos(texto).lower().strip()
    t = t.replace("'", "").replace("'", "").replace("'", "")
    t = re.sub(r"\s+", " ", t)
    return t


def _plural_candidates(clave: str) -> list[str]:
    """Candidatos singular/plural para buscar en el catálogo."""
    out = [clave]
    if len(clave) > 3 and clave.endswith("s"):
        out.append(clave[:-1])
    if len(clave) > 4 and clave.endswith("es"):
        out.append(clave[:-2])
    # únicos preservando orden
    vistos = set()
    ordenados = []
    for c in out:
        if c not in vistos:
            vistos.add(c)
            ordenados.append(c)
    return ordenados


def _plural_a_singular_basico(clave: str) -> str:
    """Heurística ligera para plurales en español (guineos → guineo)."""
    cands = _plural_candidates(clave)
    return cands[1] if len(cands) > 1 else clave


def _parsear_vocabulario(texto: str) -> dict[str, str]:
    """Parsea el archivo de vocabulario → {alias_normalizado: canonico_normalizado}."""
    alias_a_canonico: dict[str, str] = {}
    canonico_actual = None

    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("-") or linea.startswith("="):
            continue
        if linea.startswith("Producto canónico:"):
            bruto = linea.split(":", 1)[1].strip()
            # "níspero / chico" → usar la primera forma
            bruto = bruto.split("/")[0].strip()
            canonico_actual = _norm_clave(bruto)
            if canonico_actual:
                alias_a_canonico[canonico_actual] = canonico_actual
            continue
        if linea.startswith("Alias:") and canonico_actual:
            bruto = linea.split(":", 1)[1]
            for parte in bruto.split(","):
                alias = _norm_clave(parte)
                if not alias or alias in ALIAS_EXCLUIDOS:
                    continue
                # Prefiere el canónico ya registrado; no pisar con otro.
                alias_a_canonico.setdefault(alias, canonico_actual)
                singular = _plural_a_singular_basico(alias)
                if singular not in ALIAS_EXCLUIDOS:
                    alias_a_canonico.setdefault(singular, canonico_actual)
            continue

    # Ortografía frecuente → canónico si existe.
    for mal, bien in ORTOGRAFIA_COMUN.items():
        destino = alias_a_canonico.get(_norm_clave(bien), _norm_clave(bien))
        alias_a_canonico.setdefault(_norm_clave(mal), destino)

    return alias_a_canonico


def _cargar() -> dict[str, str]:
    if not VOCAB_PATH.exists():
        return dict(ORTOGRAFIA_COMUN)
    return _parsear_vocabulario(VOCAB_PATH.read_text(encoding="utf-8"))


ALIAS_A_CANONICO = _cargar()

# Alias multi-palabra ordenados de más largo a más corto (mejor match).
_ALIAS_MULTI = sorted(
    (a for a in ALIAS_A_CANONICO if " " in a),
    key=len,
    reverse=True,
)


def canonicalizar_producto(nombre: str | None) -> str | None:
    """Devuelve el nombre canónico del producto si hay alias conocido.

    - Alias exacto (incl. multi-palabra) → producto canónico.
    - Una sola palabra conocida → canónico (guineos → banano).
    - Varias palabras: si la primera es un alias conocido, se canónica
      esa cabeza y se conservan modificadores (piñas golden → pina golden).
    - Si no hay coincidencia, se devuelve el nombre normalizado tal cual.
    """
    if not nombre:
        return None

    clave = _norm_clave(nombre)
    if not clave:
        return None

    # 1) Frase completa
    if clave in ALIAS_A_CANONICO:
        return ALIAS_A_CANONICO[clave]

    tokens = clave.split()

    # 2) Una sola palabra (probar singularizaciones)
    if len(tokens) == 1:
        for cand in _plural_candidates(tokens[0]):
            if cand in ALIAS_A_CANONICO:
                return ALIAS_A_CANONICO[cand]
        return clave

    # 3) Alias multi-palabra contenido como frase completa ya cubierto;
    #    si la clave EMPIEZA con un alias multi largo, usar ese canónico.
    for alias in _ALIAS_MULTI:
        if clave == alias or clave.startswith(alias + " "):
            return ALIAS_A_CANONICO[alias]

    # 4) Cabeza conocida + modificadores (piñas golden, tomate cherry)
    cabeza = tokens[0]
    resto = tokens[1:]
    base = None
    for cand in _plural_candidates(cabeza):
        if cand in ALIAS_A_CANONICO:
            base = ALIAS_A_CANONICO[cand]
            break
    if base:
        return " ".join([base, *resto])

    return clave


def es_alias_conocido(nombre: str | None) -> bool:
    if not nombre:
        return False
    clave = _norm_clave(nombre)
    return clave in ALIAS_A_CANONICO or _plural_a_singular_basico(clave) in ALIAS_A_CANONICO
