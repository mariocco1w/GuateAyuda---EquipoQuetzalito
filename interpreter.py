"""Intérprete conversacional de GuateAyuda.

Convierte lenguaje cotidiano en información estructurada (sección 8 y 12 del
contexto). Es un parser basado en REGLAS en Python puro: sin API externa ni
claves, para que la demo nunca dependa de servicios externos (secciones 6 y 23).

IMPORTANTE (sección 12): este módulo NO realiza cálculos financieros.
Solo extrae la estructura cruda (producto, cantidad, precio, monto, existencia,
concepto). El cálculo del total lo hace la capa de servicio / backend.

Operaciones soportadas en el MVP (sección 8):
    * venta       -> "Vendí 8 almuerzos a Q25."
    * gasto       -> "Gasté Q150 comprando verduras."
    * inventario  -> "Me quedan 10 gaseosas."
    * produccion  -> "Se fabricaron 24 unidades de vasos."
Un mismo mensaje puede contener varias operaciones separadas por "y", ",",
"además" o "también" (ver `interpretar_multiples`).
"""

import re
import unicodedata
import uuid

# ---------------------------------------------------------------------------
# Palabras / verbos que indican el tipo de operación
# ---------------------------------------------------------------------------

START_PRON = (
    r"\b(vendi|vendí|vendió|vendimos|vendieron|vendi)",
    r"\b(compre|compré|compré|compró|compramos|compraron)",
    r"\b(gaste|gasté|gastamos|gastamos|pague|pagué)",
    r"\b(me queda|quedan|tengo|hay|stock|existencia|aun tengo|aún tengo)",
)

TIPO_PATTERNS = [
    # Orden importante: gasto antes que venta, porque "compré" puede indicar
    # compra de insumo (gasto) salvo que se registre como venta.
    ("inventario", r"\b(me quedar?|quedan|tengo|hay|stock|existencia|"
                    r"ingresaron|ingres[oó]|entraron|entr[oó]|recibimos|recib[íi])\b"),
    ("produccion", r"\b(fabricamos|fabricaron|fabric[oó]|producimos|produjimos|"
                   r"elaboramos|elaboraron|hicimos|hicieron|manufacturamos)\b"),
    ("gasto",      r"\b(gast[eé]|gastamos|pagu[eé]|pague|compr[eé]|compramos|compramos)\b"),
    ("venta",      r"\b(vend[ií]|vend[ií]o|vend[ií]mos|vend[ií]eron|vend[ií])\b"),
]

# Sufijos / artículos que se limpian del nombre del producto.
STOP_PRODUCTO = [
    "de", "del", "la", "las", "el", "los", "un", "una", "unos", "unas",
    "a", "cada", "quetzales", "quetzal", "q", "pesos", "gast[eé]", "gastamos",
    "compr[eé]", "compramos", "vend[ií]", "por", "hoy", "dia", "día",
    "fabricamos", "fabricaron", "fabric[oó]", "producimos", "produjimos",
    "elaboramos", "hicimos", "hicieron", "manufacturamos", "unidades",
    "se", "ingresaron", "ingres[oó]", "entraron", "recibimos",
    # Rellenos de lenguaje natural que ensucian el nombre del producto.
    "me", "mi", "en", "negocio", "empresa", "tambien", "también",
    "cantidad", "cantidades", "para", "total",
]

# ---------------------------------------------------------------------------
# Expresiones de números y moneda
# ---------------------------------------------------------------------------

QTY_RE = re.compile(r"\b(\d{1,4})\b")

MONTO_RE = re.compile(
    r"(?:Q\s*|q\s*|\$\s*)?(\d{1,6})\s*(?:quetzales?|pesos)?", re.IGNORECASE
)

# Precio unitario explícito: "a Q25", "a 25 quetzales", "Q25 cada uno"
PRECIO_UNITARIO_RE = re.compile(
    r"\ba\s*(?:Q\s*|q\s*)?(\d{1,4})(?:\s*quetzales?)?(?:\s*cada\b)?",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Consultas del asesor virtual (preguntas sobre el negocio)
# ---------------------------------------------------------------------------

# Intenciones de consulta detectadas por palabras clave (texto normalizado).
# Se priorizan ANTES que las operaciones de registro; las frases de registro
# ("tengo 10 gaseosas") no coinciden porque exigen el sustantivo de la consulta.
CONSULTA_PATTERNS = [
    ("asesor", re.compile(r"\b(quien eres|quien eres tu|quien te (creo|hizo|programo|invento)|"
                          r"como te llamas|cual es tu nombre|tu nombre|eres (un|una) (bot|ia|asistente|asesor)|"
                          r"que eres|eres inteligente)\b")),
    ("despedida", re.compile(r"\b(gracias|muchas gracias|adios|chao|chau|hasta luego|hasta pronto|"
                             r"nos vemos|buena suerte|exitos)\b")),
    ("ayuda", re.compile(r"\b(ayuda(?:me)?|que puedes hacer|que puedo (?:escribir|hacer|preguntar|consultar)|"
                         r"que preguntas puedo hacer|como (?:funciona|se usa|usar|se utiliza)|"
                         r"que funciones tienes|necesito ayuda)\b")),
    ("productos", re.compile(r"\bque productos?(?: tengo| hay| tienes| registra| manejo)?\b|"
                             r"\b(?:ver|mostrar|listar|consultar|enseña(?:me)?) (?:mis |los )?productos?\b|"
                             r"\bcuales son (?:mis |los )?productos?\b|"
                             r"\bque vendo\b|\bcuantos productos\b|\bque hay en mi negocio\b")),
    ("ventas", re.compile(r"\bcomo van (?:las |mis )?ventas\b|\bcuanto (?:he|hemos|has) vendido\b|"
                          r"\bcuantas ventas\b|\bque he vendido\b|\bventas (?:de )?(?:hoy|del dia|de esta semana|de la semana)\b|"
                          r"\btotal (?:de )?ventas\b")),
    ("gastos", re.compile(r"\bcuanto he gastado\b|\bcuantos gastos\b|\bque gastos\b|\bmis gastos\b|"
                          r"\btotal (?:de )?gastos\b|\ben que gaste\b|\bgastos (?:de )?(?:hoy|del dia|de esta semana|del mes)\b")),
    ("inventario", re.compile(r"\bque me queda\b|\bcomo esta (?:mi |el |nuestro )?(?:inventario|stock)\b|\binventario bajo\b|"
                              r"\bstock bajo\b|\bque me falta\b|\bcuanto inventario\b|\bhay (?:suficiente )?(?:inventario|stock)\b|"
                              r"\bestado del inventario\b")),
    ("resumen", re.compile(r"\bdame un resumen\b|\bda un resumen\b|\bresumen (?:de|del) (?:mi |el )?negocio\b|"
                           r"\bcomo (?:esta|anda|va) (?:mi |el |nuestro )?(?:negocio|empresa)\b|\bcomo va todo\b|"
                           r"\bestado (?:de|del) (?:mi )?negocio\b")),
]

SALUDO_RE = re.compile(r"^(hola|buenos dias|buenas tardes|buenas noches|buenas|que tal|hey|saludos|holis)"
                       r"(?:\s*[!.¿?]+\s*)*$")


def _es_saludo(mensaje):
    """True si el mensaje es únicamente un saludo."""
    return bool(SALUDO_RE.match(_normalizar(mensaje).strip()))


def _detectar_consulta(mensaje):
    """Detecta si el mensaje es una consulta y devuelve su intención o None."""
    normalizado = _normalizar(mensaje)
    for intencion, patron in CONSULTA_PATTERNS:
        if patron.search(normalizado):
            return intencion
    return None


def _consulta_de(mensaje):
    """Intención de consulta del mensaje (saludo incluido) o None."""
    if _es_saludo(mensaje):
        return "saludo"
    return _detectar_consulta(mensaje)


def _resultado_consulta(intencion, mensaje):
    """Estructura de una consulta del asesor virtual (sin token ni operación)."""
    return {
        "interpretado": True,
        "consulta": True,
        "tipo": intencion,
        "intencion": intencion,
        "mensaje_humano": mensaje,
        "token_sesion": None,
        "errores": [],
    }


def _normalizar(texto):
    """Quita acentos y normaliza a minúsculas para comparaciones."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower()


def _detectar_tipo(original):
    """Detecta el tipo de operación a partir de palabras clave."""
    normalizado = _normalizar(original)
    for tipo, patron in TIPO_PATTERNS:
        if re.search(patron, normalizado):
            return tipo
    return None


def _extraer_numeros(original):
    """Devuelve la lista de números enteros encontrados en el texto original."""
    return [int(m) for m in QTY_RE.findall(original)]


def _extraer_precio_unitario(original):
    """Busca el precio unitario con patrón 'a Q25' o similar."""
    m = PRECIO_UNITARIO_RE.search(original)
    return int(m.group(1)) if m else None


MONEDA_PEGADA_RE = re.compile(r"\bQ\s*\d+\b|\bq\s*\d+\b|\$\s*\d+\b", re.IGNORECASE)


def _limpiar_producto(texto, tipo):
    """Extrae el nombre del producto quitando ruido (verbos, artículos, números)."""
    # Quitar montos/precios pegados como "Q25" o "$25".
    resultado = MONEDA_PEGADA_RE.sub(" ", texto)
    for palabra in STOP_PRODUCTO:
        resultado = re.sub(rf"\b{palabra}\b", " ", resultado, flags=re.IGNORECASE)
    # Quitar el tipo de operación y signos de puntuación.
    resultado = re.sub(r"[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]", " ", resultado)
    palabras = [p for p in resultado.split() if p and not p.isdigit()]
    return " ".join(palabras).strip().lower() or None


def _detectar_inventario(original):
    """Parsea operaciones de inventario: 'Me quedan 10 gaseosas'."""
    numeros = _extraer_numeros(original)
    existencia = numeros[0] if numeros else None

    # El producto es todo lo que no es número ni verbo de existencia.
    texto = re.sub(r"(me\s+quedan|quedan|tengo|hay|stock|existencia|de)", " ", original, flags=re.IGNORECASE)
    producto = _limpiar_producto(texto, "inventario")

    return {
        "tipo": "inventario",
        "producto": producto,
        "existencia": existencia,
        "concepto": producto,
    }


def _detectar_gasto(original):
    """Parsea gastos: 'Gasté Q150 comprando verduras'."""
    montos = [int(m.group(1)) for m in MONTO_RE.finditer(original)]
    monto = montos[0] if montos else None

    # El concepto es todo lo que no es número, ni verbo de gasto, ni moneda.
    texto = re.sub(
        r"\b(gast[eé]|gastamos|gastando|pagu[eé]|pague|pagando|"
        r"compr[eé]|compramos|comprando|comprar|compra|q|quetzales?|pesos)\b",
        " ",
        original,
        flags=re.IGNORECASE,
    )
    concepto = _limpiar_producto(texto, "gasto")

    return {
        "tipo": "gasto",
        "monto": monto,
        "concepto": concepto,
        "descripcion": concepto,
    }


def _detectar_venta(original):
    """Parsea ventas: 'Vendí 8 almuerzos a Q25'."""
    numeros = _extraer_numeros(original)
    cantidad = numeros[0] if numeros else None
    precio_unitario = _extraer_precio_unitario(original)

    # Utilizar el segundo número como precio si el patrón 'a Qxx' no apareció.
    if precio_unitario is None and len(numeros) >= 2:
        precio_unitario = numeros[1]

    texto = re.sub(
        r"\b(vend[ií]|vend[ií]o|vend[ií]mos|vend[ií]eron|a|cada|por)\b",
        " ",
        original,
        flags=re.IGNORECASE,
    )
    producto = _limpiar_producto(texto, "venta")

    return {
        "tipo": "venta",
        "producto": producto,
        "cantidad": cantidad,
        "precio_unitario": precio_unitario,
    }


def _detectar_produccion(original):
    """Parsea producción: 'Se fabricaron 24 unidades de vasos'."""
    numeros = _extraer_numeros(original)
    cantidad = numeros[0] if numeros else None

    texto = re.sub(
        r"\b(fabricamos|fabricaron|fabric[oó]|producimos|produjimos|"
        r"elaboramos|elaboraron|hicimos|hicieron|manufacturamos|"
        r"unidades|se|de)\b",
        " ",
        original,
        flags=re.IGNORECASE,
    )
    producto = _limpiar_producto(texto, "produccion")

    return {
        "tipo": "produccion",
        "producto": producto,
        "cantidad": cantidad,
    }


def _detectar_ingreso_inventario(original):
    """Parsea ingreso de mercancía: 'Ingresaron 15 espejos'."""
    numeros = _extraer_numeros(original)
    cantidad = numeros[0] if numeros else None

    texto = re.sub(
        r"\b(ingresaron|ingres[oó]|entraron|entr[oó]|recibimos|recib[íi]|de)\b",
        " ",
        original,
        flags=re.IGNORECASE,
    )
    producto = _limpiar_producto(texto, "inventario")

    return {
        "tipo": "inventario",
        "producto": producto,
        "existencia": cantidad,
        "concepto": producto,
        "movimiento": "ENTRADA",
    }


# Separa el mensaje en cláusulas individuales cuando contiene varias
# operaciones unidas por conectores.
CLAUSULAS_RE = re.compile(r"\s+(?:y\s+|\+\s*|,\s*|;\s*|y\s+tambi[eé]n\s+|"
                          r"adem[aá]s\s+|tambi[eé]n\s+)\s*")

def _dividir_clausulas(mensaje):
    """Divide un mensaje en cláusulas aprovechando los conectores."""
    partes = CLAUSULAS_RE.split(mensaje)
    return [p.strip() for p in partes if p.strip()]


def interpretar(mensaje):
    """Convierte un mensaje de lenguaje natural en estructura.

    Devuelve un dict con:
        interpretado (bool)
        tipo (str)  su tipo de operación
        operacion (dict)  estructura detectada
        mensaje_humano (str)  el texto original
        token_sesion (str)  uuid para el flujo de confirmación
        errores (list)  advertencias si faltan campos
    """
    mensaje = (mensaje or "").strip()
    if not mensaje:
        return {
            "interpretado": False,
            "operacion": None,
            "mensaje": "No se recibió ningún mensaje.",
            "token_sesion": str(uuid.uuid4()),
        }

    # Las consultas del asesor virtual se resuelven antes que las operaciones.
    consulta = _consulta_de(mensaje)
    if consulta:
        return _resultado_consulta(consulta, mensaje)

    tipo = _detectar_tipo(mensaje)

    if tipo == "inventario":
        # Distinguir ingreso de mercancía (mueve la existencia hacia arriba)
        # frente a declaración de existencia actual.
        if re.search(r"\b(ingresaron|ingres[oó]|entraron|entr[oó]|recibimos|recib[íi])\b",
                     _normalizar(mensaje)):
            operacion = _detectar_ingreso_inventario(mensaje)
        else:
            operacion = _detectar_inventario(mensaje)
    elif tipo == "produccion":
        operacion = _detectar_produccion(mensaje)
    elif tipo == "gasto":
        operacion = _detectar_gasto(mensaje)
    elif tipo == "venta":
        operacion = _detectar_venta(mensaje)
    else:
        return {
            "interpretado": False,
            "tipo": None,
            "operacion": None,
            "mensaje": (
                "No pude identificar la operación. "
                "Ejemplos: 'Vendí 8 almuerzos a Q25', "
                "'Gasté Q150 comprando verduras', 'Me quedan 10 gaseosas'."
            ),
            "token_sesion": str(uuid.uuid4()),
        }

    # Validación mínima: al menos un dato clave presente.
    errores = _validar(operacion)

    return {
        "interpretado": not errores,
        "tipo": operacion["tipo"],
        "operacion": operacion,
        "mensaje_humano": mensaje,
        "token_sesion": str(uuid.uuid4()),
        "errores": errores,
    }


def _validar(operacion):
    """Devuelve lista de errores si faltan campos esenciales."""
    errores = []
    tipo = operacion.get("tipo")
    if tipo == "venta":
        if not operacion.get("cantidad"):
            errores.append("Falta la cantidad vendida.")
        if not operacion.get("producto"):
            errores.append("Falta el producto.")
    elif tipo == "gasto":
        if not operacion.get("monto"):
            errores.append("Falta el monto del gasto.")
    elif tipo == "inventario":
        if operacion.get("existencia") is None:
            errores.append("Falta la existencia registrada.")
    elif tipo == "produccion":
        if not operacion.get("cantidad"):
            errores.append("Falta la cantidad producida.")
        if not operacion.get("producto"):
            errores.append("Falta el producto fabricado.")
    return errores


def interpretar_multiples(mensaje):
    """Interpreta un mensaje que puede contener varias operaciones.

    Divide el texto en cláusulas y devuelve una lista de resultados, uno por
    cada operación detectada. Si el mensaje completo es una consulta del asesor
    virtual, devuelve una lista con un único resultado `consulta=True`. Si no
    se identifica nada, devuelve una lista con un único resultado
    `interpretado=False`.
    """
    texto = (mensaje or "").strip()

    if not texto:
        return [{
            "interpretado": False,
            "operacion": None,
            "mensaje": "No se recibió ningún mensaje.",
            "token_sesion": str(uuid.uuid4()),
        }]

    # Si el mensaje completo es una consulta, se responde como una sola.
    consulta = _consulta_de(texto)
    if consulta:
        return [_resultado_consulta(consulta, texto)]

    clausulas = _dividir_clausulas(texto)
    resultados = []
    for clausula in clausulas:
        resultados.append(interpretar(clausula))

    # Descartar saludos puros si el mensaje también trae otra operación.
    if len(resultados) > 1:
        con_contenido = [r for r in resultados
                         if not (r.get("consulta") and r.get("tipo") == "saludo")]
        if con_contenido:
            resultados = con_contenido

    return resultados
