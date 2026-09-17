"""Intérprete conversacional de GuateAyuda.

Convierte lenguaje cotidiano en información estructurada. Es un parser basado
en REGLAS en Python puro: sin API externa ni claves, para que la demo nunca
dependa de servicios externos.

ARQUITECTURA (INTENCIÓN + CONTEXTO + ENTIDADES + VALIDACIÓN):

    mensaje del usuario
        ↓
    normalización del texto
        ↓
    detección de intención (SALE / PURCHASE / ...)
        ↓
    extracción de entidades (producto, cliente, proveedor, cantidad, precio)
        ↓
    clasificación de roles (cliente vs proveedor según la intención)
        ↓
    validación + confianza
        ↓
    estructura estructurada (para confirmación del usuario)

El producto SIEMPRE es una entidad independiente. Nunca se construye
concatenando la frase completa: el nombre del producto proviene únicamente del
fragmento identificado semánticamente como PRODUCT.

Intenciones soportadas:
    * venta        ->  "A José le vendí 120 piñas a Q12"   (SALE)
    * compra       ->  "Compré 100 tomates a Don Pedro a Q5"  (PURCHASE)
    * gasto        ->  "Gasté Q150 comprando verduras"
    * inventario   ->  "Me quedan 10 gaseosas" / "Ingresaron 15 espejos"
    * produccion   ->  "Se fabricaron 24 unidades de vasos"
    * consultas    ->  saludo, ayuda, productos, ventas, gastos, inventario,
                       resumen, asesor, despedida, prediccion, inventario_riesgo,
                       anomalias, recomendaciones

Un mismo mensaje puede contener varias operaciones separadas por "y", ",",
"además" o "también" (ver `interpretar_multiples`).

Este módulo NO realiza cálculos financieros. Solo extrae la estructura cruda.
El cálculo del total lo hace la capa de servicio / backend.
"""

import re
import unicodedata
import uuid

from vocabulario_productos import canonicalizar_producto

# ---------------------------------------------------------------------------
# Palabras / verbos que indican el tipo de operación
# ---------------------------------------------------------------------------

# Verbos y expresiones de VENTA (sección 6 del plan).
# IMPORTANTE: "me compró / me compraron" indica que el negocio vendió.
VERBOS_VENTA = re.compile(
    r"\b(vendi|vendio|vendimos|vendieron|vend[ée]|vendiste|vender|venderle|venderles|"
    r"comercialic|comercializ|coloq(?:u[eé]|amos|o)|coloc(?:o|o)|despach(?:e|o|amos)?|"
    r"entreg(?:ue|o|amos)?|factur(?:e|o|amos)?|"
    r"realic(?:e|amos|o)? una venta|hice una venta|tuve una venta|"
    r"cerre una venta|concrete una venta|salio venta|salo venta|"
    r"sali(?:o|eron)|se llevo|se llevaron|me compraron|me compro|"
    r"mov(?:i|io|imos|ieron) unidades|colocacion|despacho)\b",
    re.IGNORECASE,
)

# Verbos y expresiones de COMPRA (sección 7 del plan).
VERBOS_COMPRA = re.compile(
    r"\b(compre|compramos|comprar|adquir(?:i|io|e|imos)|abastec(?:i|io|imos)?|"
    r"surt(?:i|o|imos)?|consegui|consegu(?:i|imos)?|"
    r"ped(?:i|io|imos)|encarg(?:ue|o|amos)?|"
    r"hice una compra|realice una compra|compre producto|compre mercaderia|"
    r"compre inventario|adquiri productos|surto inventario|surti inventario|"
    r"abasteci el negocio|hice un pedido|recibi mercaderia|"
    r"reabasteci|reabastecio|recarga|recargue|cargue mercaderia)\b",
    re.IGNORECASE,
)

# Formas de tercera persona que significan "otra persona compró (de nosotros)"
# -> el negocio vendió (cliente = esa persona).
COMPRA_TERCERA_PERSONA = re.compile(
    r"\b(compro|compraron|compra|comprando)\b", re.IGNORECASE
)

# Palabras de contexto que se excluyen del producto (sin blacklist ciega:
# solo se quitan cuando cumplen rol gramatical; los productos legítimos que
# contienen palabras similares se conservan porque se extraen por posición).
STOP_CONTEXTO = {
    "a", "al", "la", "las", "el", "los", "le", "les", "para", "por", "con",
    "de", "del", "en", "un", "una", "unos", "unas", "uno", "cada", "que", "y", "se",
    "me", "mi", "hoy", "dia", "día", "tambien", "también", "cantidad",
    "cantidades", "total", "mejor", "negocio", "empresa", "cliente", "clienta",
    "proveedor", "proveedora", "nuevo", "nueva", "recien", "recién",
    "unidad", "unidades", "pieza", "piezas", "caja", "cajas", "bolsa",
    "bolsas", "costal", "costales", "saco", "sacos", "lote", "lotes",
    "paquete", "paquetes", "bulto", "bultos", "docena", "docenas",
    "libra", "libras", "quintal", "quintales", "arroba", "arrobas",
    "quetzal", "quetzales", "peso", "pesos", "gtq",
    "inventario", "stock", "mercaderia", "mercaderias", "producto", "productos",
    "pedido", "pedidos", "articulo", "articulos", "encargo", "encargos",
    "venta", "ventas",
    # Palabras adicionales de contexto que no deben ser producto
    "su", "sus", "ese", "esa", "esos", "esas", "este", "esta", "estos", "estas",
    "aquel", "aquella", "aquellos", "aquellas", "lo", "los", "las",
    "del", "al", "haul", "aqui", "alla", "ahi", "como", "cuando", "donde",
    "porque", "por que", "pues", "entonces", "mas", "menos", "muy",
    "tan", "tanto", "tanta", "tantos", "tantas",
    # Palabras de operación
    "dia", "hoy", "ayer", "mañana", "semana", "mes", "ano",
    "momento", "ahora", "luego", "pronto", "tarde", "temprano",
    # Números como contexto
    "primera", "primero", "segunda", "segundo", "tercera", "tercero",
}

# --------- Unidades de medida ---------
UNIDADES_RE = re.compile(
    r"\b(unidades?|piezas?|cajas?|bolsas?|costales?|sacos?|lotes?|paquetes?|"
    r"bultos?|documentos?|gramos|kilogramos?|kilos?|libras?|lb|"
    r"quintales?|arrobas?|toneladas?|litros?|mililitros?|galones?|docenas?)\b",
    re.IGNORECASE,
)

# --------- Prefijos y sufijos de personas ---------
TRATAMIENTOS = {"don", "doña", "don", "dona", "lic", "licencia", "dr", "sra", "sr"}

PERSONAS_CONOCIDAS = (
    "jose", "maria", "carlos", "pedro", "juan", "luis", "luisa", "ana",
    "marta", "rosa", "miguel", "antonio", "jorge", "francisco", "manuel",
    "ramon", "ricardo", "ernesto", "hernesto", "elena", "sofia", "carmen",
    "diego", "pablo", "andres", "david", "javier", "oscar", "carlos",
    # Nombres guatemaltecos comunes
    "raul", "roberto", "hector", "edgar", "edwin", "byron", "aldair",
    "marvin", "brayan", "anderson", "kevin", "lester", "rodolfo", "alejandro",
    "arturo", "guillermo", "alvaro", "sergio", "rafael", "rafa",
    "beatriz", "gloria", "lucia", "patricia", "claudia", "veronica",
    "sandra", "laura", "diana", "karla", "gabriela", "ada", "irma",
    "jazmin", "iris", "norma", "teresa", "rosario", "flor",
    "tomas", "martin", "enrique", "alberto", "armando", "raul",
    "saul", "israel", "moises", "jonathan", "josefina", "ana maria",
    "marco", "rodrigo", "felipe", "gabriel", "sebastian", "lucas",
    "mateo", "miguel angel", "juan carlos", "juan jose", "maria jose",
    "maria luisa", "maria teresa",
)

# --------- Negocios / entidades comerciales como cliente o proveedor ---------
NEGOCIOS = (
    "tienda", "almacen", "supermercado", "mercado", "puesto", "restaurante",
    "comedor", "cafeteria", "panaderia", "carniceria", "verduleria",
    "fruteria", "negocio", "empresa", "distribuidor", "distribuidora",
    "mayorista", "minorista", "proveedor", "finca", "productor", "farmacia",
    "heladeria", "licoreria", "polleria", "tortilleria", "molinera",
    "abarrotes", "miscelanea", "minisuper", "colmado", "bodega",
    "ferreteria", "papeleria", "libreria", "zapateria", "boutique",
    "lavanderia", "rectificadoras", "taller", "mecanica", "gasolinera",
    "estacion", "clinica", "consultorio", "gimnasio", "estudio",
    "hotel", "hostal", "finca", "hacienda", "vivero", "invernadero",
    "cooperativa", "asociacion", "fundacion",
)

# ---------------------------------------------------------------------------
# Números escritos y unidades
# ---------------------------------------------------------------------------

# Números escritos (sección 11).
NUMEROS_ESCRITOS = {
    "cero": 0, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200, "trescientos": 300,
    "trescientas": 300, "cuatrocientos": 400, "cuatrocientas": 400,
    "quinientos": 500, "quinientas": 500, "seiscientos": 600, "setecientos": 700,
    "ochocientos": 800, "novecientos": 900, "mil": 1000, "millon": 1000000,
    # Compuestos comunes
    "veintiuno": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28,
    "veintinueve": 29,
    "treinta y uno": 31, "cuarenta y cinco": 45, "cincuenta y dos": 52,
    "sesenta y tres": 63, "setenta y ocho": 78, "ochenta y nueve": 89,
    "noventa y nueve": 99, "dos mil": 2000, "tres mil": 3000, "cinco mil": 5000,
    "diez mil": 10000, "veinte mil": 20000, "cien mil": 100000,
    "quinientos": 500, "un millon": 1000000,
}

# Expresiones compuestas de cantidad (sección 11).
CANTIDAD_COMPUESTA_RE = re.compile(
    r"\b(una\s+docena|media\s+docena|dos\s+mil|tres\s+mil|"
    r"cinco\s+mil|diez\s+mil|veinte\s+mil|cien\s+mil|"
    r"(?:una|un)\s+docena)\b", re.IGNORECASE)
CANTIDAD_UNIDAD_RE = re.compile(
    r"\b(una|dos|tres|cuatro|cinco|diez|veinte|treinta|cien|ciento)\s+"
    r"(unidad|unidades|pieza|piezas|caja|cajas|bolsa|bolsas|kilo|kilos|"
    r"libra|libras|docena|docenas)\b", re.IGNORECASE)

QTY_DIGIT_RE = re.compile(r"\b(\d{1,5})\b")

MONEDA_RE = re.compile(r"\b(q|gtq|quetzal|quetzales|)\s*(\d{1,6})\b", re.IGNORECASE)
Q_PEGADA_RE = re.compile(r"\bq\s*\d{1,6}\b|\bQ\s*\d{1,6}\b", re.IGNORECASE)

# Precio unitario explícito.
PRECIO_UNITARIO_RE = re.compile(
    r"\b(?:a|por|cada|unidad)\s*(?:q\s*|gtq\s*|quetzales?\s*)?(\d{1,5})"
    r"(?:\s*(?:quetzales?|q))?(?:\s*cada\s*(?:uno|una)?)?",
    re.IGNORECASE,
)
PRECIO_CADA_RE = re.compile(
    r"(?:q\s*)?(\d{1,5})\s*(?:cada\s*(?:uno|una|unidad)|la\s*unidad|"
    r"por\s*unidad|por\s*la\s*unidad|la\s*pieza|el\s*(?:kilo|kilogramo|quintal))",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Consultas del asesor virtual (preguntas sobre el negocio)
# ---------------------------------------------------------------------------

CONSULTA_PATTERNS = [
    # Inteligencia (FASE 7): predicción, riesgo de inventario, anomalías y
    # recomendaciones. Van al inicio para no ser capturadas por consultas
    # genéricas (ventas / inventario / productos). El texto ya está
    # normalizado (sin acentos), por lo que los patrones no los requieren.
    ("prediccion", re.compile(
        r"\b(predic(?:ci|e|ir|ij)|pronostic|proyecci|estim(?:acion|ar|o|as))\w*\b|"
        r"\bcuanto (?:voy a vender|vender[eé]|crees que (?:vender[eé]|venda|vender[a-z]*)|"
        r"estimas que (?:vender[eé]?|venda|vender[a-z]*)|me (?:tocara|toca|va a tocar) vender)\b|"
        r"\b(?:cual|como|cuales) (?:sera|seran|estara|estaran) "
        r"(?:mi|mis|las|nuestras|los) (?:venta|ventas|pronostico)\b|"
        r"\bcomo van a estar (?:mis |las |nuestras )?(?:venta|ventas)\b|"
        r"\bventas (?:de los )?proximos dias\b|"
        r"\bventas (?:a )?futuro\b|\bventas futuras\b")),
    ("inventario_riesgo", re.compile(
        r"\b(?:riesgo|agotamiento|reposicion)\b.*\b(?:inventario|stock|productos?)\b|"
        r"\b(?:inventario|stock|productos?)\b.*\b(?:riesgo|agotarse|agotamiento|reposicion)\b|"
        r"\bcuando.*(?:agot|se agota)\b|"
        r"\bcuantos dias (?:de )?inventario\b|"
        r"\bque (?:productos?|me) (?:se )?(?:van|va) a agotar\b|"
        r"\bse me van? a agotar\b|"
        r"\bque me va a faltar\b")),
    ("anomalias", re.compile(
        r"\banomalias?\b|"
        r"\b(?:dia|movimiento|venta|gasto|precio|operacion)\b.*"
        r"\b(?:raro|rara|anormal|inusual|sospechoso|sospechosa|extrano|extrana)\b|"
        r"\bfuera de lo normal\b|"
        r"\balgo (?:raro|rara|anormal|inusual|sospechoso|sospechosa|extrano|extrana)\b|"
        r"\bcomportamiento inusual\b")),
    ("recomendaciones", re.compile(
        r"\brecom(?:i?end|ienda)[a-z]*\b|"
        r"\bque (?:me )?sugieres\b|\bque sugeririas?\b|\bsugerencias?\b|"
        r"\bconsejos?\b|"
        r"\bque deberia (?:hacer|revisar|mejorar)\b|"
        r"\bcomo (?:puedo|podria) mejorar\b|"
        r"\bque me conviene\b")),
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
                             r"\bque vendo\b|\bcuantos productos\b|\bque hay en mi negocio\b|"
                             r"\bproducto.*estrella\b|\bproducto.*mas vendido\b|\bmejor.*producto\b|"
                             r"\bproducto.*top\b|\bque productos manejo\b")),
    ("ventas", re.compile(r"\bcomo van (?:las |mis )?ventas\b|\bcuanto (?:he|hemos|has) vendido\b|"
                          r"\bcuantas ventas\b|\bque he vendido\b|\bventas (?:de )?(?:hoy|del dia|de esta semana|de la semana)\b|"
                          r"\btotal (?:de )?ventas\b|\bcuanto.*le vendi\b|\bcuanto vendi\b|"
                          r"\bresumen.*ventas\b|\bver.*ventas\b|\bmostrar.*ventas\b|"
                          r"\bventas.*hoy\b|\bventas.*semana\b|\bventas.*mes\b")),
    ("gastos", re.compile(r"\bcuanto he gastado\b|\bcuantos gastos\b|\bque gastos\b|\bmis gastos\b|"
                          r"\btotal (?:de )?gastos\b|\ben que gaste\b|\bgastos (?:de )?(?:hoy|del dia|de esta semana|del mes)\b|"
                          r"\bcuanto.*compr\b|\bque.*compr\b|\bcompras.*hoy\b|\bcompras.*semana\b|"
                          r"\btotal.*compras\b|\binversion\b|\bgasto.*compr\b")),
    ("inventario", re.compile(r"\bque me queda\b|\bcomo esta (?:mi |el |nuestro )?(?:inventario|stock)\b|\binventario bajo\b|"
                              r"\bstock bajo\b|\bque me falta\b|\bcuanto inventario\b|\bhay (?:suficiente )?(?:inventario|stock)\b|"
                              r"\bestado del inventario\b|\bver.*inventario\b|\bmostrar.*inventario\b|"
                              r"\binventario.*hoy\b|\bstock.*hoy\b|\bnecesito.*reabastecer\b|"
                              r"\breponer\b|\bfalta.*producto\b")),
    ("resumen", re.compile(r"\bdame un resumen\b|\bda un resumen\b|\bresumen (?:de|del) (?:mi |el )?negocio\b|"
                           r"\bcomo (?:esta|anda|va) (?:mi |el |nuestro )?(?:negocio|empresa)\b|\bcomo va todo\b|"
                           r"\bestado (?:de|del) (?:mi )?negocio\b|\breporte\b|\breporte.*general\b")),
]

SALUDO_RE = re.compile(r"^(hola|buenos dias|buenas tardes|buenas noches|buenas|que tal|hey|saludos|holis)"
                       r"(?:\s*[!.¿?]+\s*)*$")


# ---------------------------------------------------------------------------
# Normalización (sección 1)
# ---------------------------------------------------------------------------

def _quitar_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def _normalizar(texto):
    """Quita acentos y normaliza a minúsculas para comparaciones."""
    return _quitar_acentos(texto).lower()


def _convierte_numeros_escritos(normalizado):
    """Reemplaza números escritos por su valor numérico (token por token).

    Devuelve una nueva cadena donde las palabras numéricas se sustituyen por
    su equivalente, p.ej. 'veinte pinas' -> '20 pinas'. Respeta expresiones
    compuestas como 'dos mil' o 'una docena'.
    """
    resultado = normalizado

    # Expresiones compuestas explicitas primero: "una docena" -> 12,
    # "media docena" -> 6, "dos mil" -> 2000, "tres mil" -> 3000.
    def _reemplazo_compuesto(m):
        palabra = _quitar_acentos(m.group(0).strip().lower())
        if "docena" in palabra:
            if "media" in palabra:
                return "6"
            return "12"
        # "X mil" -> X * 1000
        if "mil" in palabra:
            partes = palabra.split()
            if partes and partes[0].isdigit():
                return str(int(partes[0]) * 1000)
            # numero escrito + mil: "dos mil" -> 2000
            if partes and partes[0] in NUMEROS_ESCRITOS:
                return str(int(NUMEROS_ESCRITOS[partes[0]]) * 1000)
        return palabra
    resultado = CANTIDAD_COMPUESTA_RE.sub(_reemplazo_compuesto, resultado)

    # Expresiones de cantidad con unidad ("una caja", "una unidad") -> "1 caja".
    def _reemplazo_unidad(m):
        num = "1"
        unidad = m.group(2).strip()
        return f"{num} {unidad}"
    resultado = re.sub(
        r"\buna?\s+(unidad|unidades|pieza|piezas|caja|cajas|bolsa|bolsas|"
        r"kilo|kilos|libra|libras|costal|costales|saco|sacos)\b",
        _reemplazo_unidad, resultado, flags=re.IGNORECASE)

    # Expresiones "treinta y cinco", "cuarenta y dos" -> 35, 42
    # (decenas + 'y' + unidades).
    DECENAS = {
        "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50,
        "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
    }
    def _reemplazo_compuesto_num(m):
        decena = DECENAS.get(m.group(1))
        unidad = NUMEROS_ESCRITOS.get(m.group(2))
        if decena is not None and unidad is not None:
            return str(decena + unidad)
        return m.group(0)
    resultado = re.sub(
        r"\b(veinte|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa)"
        r"\s+y\s+(uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\b",
        _reemplazo_compuesto_num, resultado, flags=re.IGNORECASE)

    palabras = resultado.split()
    nuevos = []
    for palabra in palabras:
        clave = _quitar_acentos(palabra.lower())
        if clave in NUMEROS_ESCRITOS:
            nuevos.append(str(NUMEROS_ESCRITOS[clave]))
        else:
            nuevos.append(palabra)
    return " ".join(nuevos)


# ---------------------------------------------------------------------------
# Intención (secciones 2, 6 y 7)
# ---------------------------------------------------------------------------

def _detectar_intencion(normalizado):
    """Devuelve la intención canónica (SALE, PURCHASE, ...) o None.

    Resuelve el conflicto 'compró':
      - 'me compró / me compraron / X compró' -> SALE (el negocio vendió).
      - 'compré / compré ... a X' -> PURCHASE (el negocio compró).
    """
    # Las consultas (preguntas) tienen prioridad: nunca registrar un gasto o
    # venta cuando el usuario está haciendo una pregunta. Detectar por la
    # presencia de pronombres/palabras interrogativas + verbo.
    es_pregunta = bool(re.search(
        r"\b(cu[aá]nto|cua[aá]l|cual|cua[aá]les|cu[aá]ntos|cu[aá]ntas|"
        r"que|cómo|como|donde|mejor|top|resumen|reporte)\b", normalizado))

    # Consultas de ventas
    if re.search(r"\b(cu[aá]nto.*vend|cu[aá]ntas ventas|que he vendido|"
                 r"ventas.*(hoy|dia|semana|mes)|total.*ventas|"
                 r"cu[aá]nto.*le vend|cu[aá]nto.*vend[ie]|"
                 r"como van.*ventas|resumen.*ventas)\b", normalizado):
        return "SALES_QUERY"

    # Consultas de compras / gastos
    if re.search(r"\b(cu[aá]nto.*gast|cu[aá]nto.*compr|cu[aá]ntas compras|"
                 r"que.*compr|compras.*(hoy|dia|semana|mes)|total.*compras|"
                 r"cu[aá]nto.*invert|inversion|gasto.*compr|"
                 r"cu[aá]nto.*gaste|cuanto.*gastado)\b", normalizado):
        return "PURCHASE_QUERY"

    # Consultas de productos
    if re.search(r"\b(que productos|cu[aá]l.*mas vendido|producto.*estrella|"
                 r"producto.*top|mejor.*producto|producto.*mas|"
                 r"que vendo|cu[aá]ntos productos|cuales son.*productos)\b", normalizado):
        return "PRODUCT_QUERY"

    # GASTO explícito ("Gasté Q150 comprando verduras", "Pagueré Q20") tiene
    # prioridad sobre 'comprando' que podría confundirse con compra/venta.
    if re.search(r"\b(gast[eé]|gastamos|pagu[eé]|pague)\b", normalizado):
        return "EXPENSE"

    # Tercera persona comprando -> SALE (le vendimos nosotros).
    if COMPRA_TERCERA_PERSONA.search(normalizado) and not VERBOS_VENTA.search(normalizado):
        if re.search(r"\b(compro|compraron|comprando)\b", normalizado):
            return "SALE"
        return "PURCHASE"

    if VERBOS_VENTA.search(normalizado):
        return "SALE"
    if VERBOS_COMPRA.search(normalizado):
        return "PURCHASE"

    # Consultas sobre inventario (preguntas con "qué me queda", "cuántas...")
    if re.search(r"\b(me quedar?|quedan|tengo|hay|stock|existencia|"
                 r"ingresaron|ingres[oó]|entraron|entr[oó]|recibimos|recib[ií]|"
                 r"agreg(?:ue|u[eé]|amos|ar)|a[nñ]ad(?:i|í|imos|ir)|"
                 r"registre|registr[eé]|registrar)\b", normalizado):
        # Detectar si es consulta (pregunta) vs registro
        if es_pregunta or re.search(r"\b(cu[aá]nto|cu[aá]ntos|cu[aá]ntas|que|cual|como|donde)\b", normalizado):
            return "INVENTORY_QUERY"
        return "INVENTORY"

    if re.search(r"\b(fabricamos|fabricaron|fabric[oó]|producimos|produjimos|produje|"
                 r"elaboramos|elaboraron|hicimos|hicieron|manufacturamos)\b", normalizado):
        return "PRODUCTION"

    # Consultas de inventario general
    if es_pregunta and re.search(r"\b(inventario|stock|que me queda|que me falta|falta|"
                 r"reabastecer|reponer)\b", normalizado):
        return "INVENTORY_QUERY"

    return None


def _intencion_a_tipo(intencion):
    """Mapea intención canónica al `tipo` legible (compatibilidad)."""
    return {
        "SALE": "venta",
        "PURCHASE": "compra",
        "INVENTORY": "inventario",
        "PRODUCTION": "produccion",
        "EXPENSE": "gasto",
        "SALES_QUERY": "ventas",
        "PURCHASE_QUERY": "gastos",
        "PRODUCT_QUERY": "productos",
        "INVENTORY_QUERY": "inventario",
    }.get(intencion, intencion.lower() if intencion else None)


# ---------------------------------------------------------------------------
# Extracción de entidades de venta/compra (secciones 3, 4, 5, 9, 10, 11, 12, 13)
# ---------------------------------------------------------------------------

def _tokenizar(normalizado):
    """Devuelve la lista de tokens normalizados (palabras y números aparte)."""
    return normalizado.split()


def _es_persona(palabra):
    """True si la palabra es un nombre propio de persona conocido."""
    p = _quitar_acentos(palabra.lower())
    return p in PERSONAS_CONOCIDAS


def _es_negocio(palabra):
    p = _quitar_acentos(palabra.lower())
    return p in NEGOCIOS


def _extraer_cantidad(normalizado, tokens):
    """Extrae (cantidad, unidad) del texto normalizado.

    La cantidad es el primer número (no monetario). La unidad es la palabra
    de medida que sigue a la cantidad.
    """
    # Números: cualquier token numérico que no forme parte de un precio (Q..).
    cantidad = None
    unidad = None
    for i, tok in enumerate(tokens):
        if re.fullmatch(r"\d{1,5}", tok):
            if i > 0 and re.search(r"\bq\b", tokens[i - 1].lower()):
                # precedido por 'q' -> es precio, no cantidad
                continue
            # evitar tomar un precio "a q12" -> q está pegado, no separado
            cantidad = int(tok)
            # unidad tras la cantidad
            if i + 1 < len(tokens) and UNIDADES_RE.fullmatch(tokens[i + 1]):
                unidad = _quitar_acentos(tokens[i + 1].lower())
            break
    return cantidad, unidad


def _extraer_precio(normalizado):
    """Extrae el precio unitario del texto normalizado (o None)."""
    # "Q15 cada una" o "15 cada una" (precio junto a 'cada')
    m = PRECIO_CADA_RE.search(normalizado)
    if m:
        return int(m.group(1))

    # "a q12", "por q12", "a 12 quetzales"
    m = PRECIO_UNITARIO_RE.search(normalizado)
    if m:
        return int(m.group(1))

    # "q12" pegado
    m = re.search(r"\bq\s*(\d{1,5})\b", normalizado)
    if m:
        return int(m.group(1))
    return None


def _extraer_persona(contexto):
    """Busca y devuelve una persona o entidad comercial en el fragmento.
    Devuelve el nombre limpio o None.

    Captura también entidades compuestas como "almacén de José" o
    "puesto de María".
    """
    contexto = contexto.strip()
    if not contexto:
        return None

    palabras = contexto.split()

    # Patrón: [negocio] 'de' [persona]  -> "almacen de jose", "puesto de maria"
    for i, w in enumerate(palabras):
        base = _quitar_acentos(w.lower())
        if _es_negocio(w) and i + 2 < len(palabras):
            sig1 = _quitar_acentos(palabras[i + 1].lower())
            if sig1 == "de" and _es_persona(palabras[i + 2]):
                return " ".join(palabras[i:i + 3]).capitalize()

    # Buscar nombres compuestos completos primero (ej: "juan carlos",
    # "maria jose") que estén en PERSONAS_CONOCIDAS como frases.
    texto_lower = " ".join(_quitar_acentos(p.lower()) for p in palabras)
    nombres_compuestos = [n for n in PERSONAS_CONOCIDAS if " " in n]
    for nc in sorted(nombres_compuestos, key=len, reverse=True):
        if nc in texto_lower:
            idx = texto_lower.find(nc)
            inicio = len(texto_lower[:idx].split())
            return " ".join(palabras[inicio:inicio + len(nc.split())]).capitalize()

    # Buscar un nombre propio conocido o un tratamiento (don/doña) + nombre.
    for i, w in enumerate(palabras):
        base = _quitar_acentos(w.lower())
        if base in TRATAMIENTOS and i + 1 < len(palabras):
            nombre = palabras[i + 1]
            if _es_persona(nombre):
                return " ".join(palabras[i:i + 2]).capitalize()
        if _es_persona(w):
            nombre = [w]
            for j in range(i + 1, min(i + 3, len(palabras))):
                pj = _quitar_acentos(palabras[j].lower())
                if _es_persona(palabras[j]) and not _es_negocio(palabras[j]):
                    nombre.append(palabras[j])
                else:
                    break
            return " ".join(nombre).capitalize()
        if _es_negocio(w):
            return w.capitalize()
    return None


def _es_verbo(palabra):
    """True si la palabra es parte de un verbo/expresión de venta o compra."""
    p = _quitar_acentos(palabra.lower())
    # Verbo de operación comercial (incluye expresiones de la sección 6 y 7).
    return bool(
        VERBOS_VENTA.search(r"\b" + p + r"\b") or
        VERBOS_COMPRA.search(r"\b" + p + r"\b") or
        p in {
            # verbos / expresiones de venta
            "vendi", "vendio", "vendimos", "vendieron", "vende", "vendiste",
            "vender", "venderle", "venderles", "comercialice", "comercializo",
            "coloque", "coloco", "colocamos", "despache", "despacho",
            "despachamos", "entregue", "entrego", "entregamos", "facture",
            "facturo", "facturamos", "llevo", "llevaron", "salio", "salieron",
            "sali",
            # verbos / expresiones de compra
            "compre", "compramos", "compro", "compraron", "comprando",
            "comprar", "adquiri", "adquirio", "abasteci", "surto", "surti",
            "consegui", "pedi", "pidio", "pedimos", "encargue", "encargo",
            "hice", "compre", "compramos", "recibi",
            # verbos adicionales
            "reabasteci", "reabastecio", "recargue", "cargue",
            "fabricamos", "fabricaron", "fabrico", "producimos",
            "elaboramos", "elaboraron", "manufacturamos",
            "gaste", "gastamos", "pague", "pagamos",
        }
    )


def _extraer_producto(fragmento_normalizado, cantidad, precio, cliente):
    """Extrae el nombre del producto del fragmento restante.

    Regla fundamental (sección 4): el producto es lo que NO es verbo, ni
    cantidad, ni precio, ni cliente, ni unidad, ni palabra de contexto.
    Nunca se construye concatenando la frase completa.

    Para productos compuestos (ej: "piñas golden", "café molido"), se unen
    las palabras que sobran después del filtrado, pero se valida que no
    excedan 4 palabras.
    """
    if not fragmento_normalizado:
        return None

    # Quitar números (cantidad/precio que hayan quedado).
    texto = QTY_DIGIT_RE.sub(" ", fragmento_normalizado)
    # Quitar moneda pegada tipo q12.
    texto = Q_PEGADA_RE.sub(" ", texto)

    palabras = [w for w in texto.split() if w]
    resultado = []
    for w in palabras:
        base = _quitar_acentos(w.lower())
        if base.isdigit():
            continue
        if _es_verbo(w):
            continue
        if base in STOP_CONTEXTO:
            continue
        if UNIDADES_RE.fullmatch(w):
            continue
        # no dejar la persona detectada dentro del producto
        if cliente and base in _quitar_acentos(cliente.lower()).split():
            continue
        # Excluir palabras que son claramente precios (q pegado a número)
        if re.match(r"^q\d", base):
            continue
        resultado.append(w)

    # Filtrar nombres de producto demasiado largos (probablemente no es producto).
    if len(resultado) > 4:
        return None
    producto = " ".join(resultado).strip(" .,").strip()
    if not producto:
        return None
    # Validación final: el producto no debe contener números ni ser demasiado largo
    producto_limpio = _quitar_acentos(producto).strip(" .,").strip()
    if len(producto_limpio) > 40:
        return None
    return canonicalizar_producto(producto_limpio)


def _clasificar_rol(intencion, persona):
    """Según la intención, la persona es cliente o proveedor (sección 5)."""
    if intencion == "SALE":
        return persona, None
    if intencion == "PURCHASE":
        return None, persona
    return persona, None


def _detectar_venta_compra(original, intencion):
    """Parsea ventas y compras con separación de entidades por posición.

    Devuelve la `operacion` con cliente/proveedor, producto, cantidad,
    unidad, precio.
    """
    normalizado = _normalizar(original)
    normalizado_numeros = _convierte_numeros_escritos(normalizado)

    # Fragmento del que extraer persona: la parte que sigue a la intención
    # o la oración completa si la intención está implícita.
    persona = _extraer_persona(normalizado_numeros)

    # Cantidad y unidad.
    tokens = normalizado_numeros.split()
    cantidad, unidad = _extraer_cantidad(normalizado_numeros, tokens)

    # Precio unitario.
    precio = _extraer_precio(normalizado_numeros)

    # Cliente / proveedor según la intención.
    cliente, proveedor = _clasificar_rol(intencion, persona)

    # Extraer producto: el fragmento sin persona, sin verbos.
    # Construir fragmento a partir de todo el texto, quitando la persona.
    fragmento = normalizado_numeros
    if persona:
        for pieza in persona.lower().split():
            fragmento = re.sub(rf"\b{re.escape(pieza)}\b", " ", fragmento)
    producto = _extraer_producto(fragmento, cantidad, precio, persona)

    return {
        "producto": producto,
        "cantidad": cantidad,
        "unidad": unidad,
        "precio_unitario": precio,
        "cliente": cliente,
        "proveedor": proveedor,
    }


# ---------------------------------------------------------------------------
# Validación y confianza (secciones 17, 18)
# ---------------------------------------------------------------------------

def _no_es_producto_valido(producto):
    """True si el 'producto' detectado parece una frase, no un producto real.

    Validaciones de la sección 17:
    1. ¿El nombre contiene números?
    2. ¿Contiene precios?
    3. ¿Contiene símbolos monetarios?
    4. ¿Es demasiado largo para ser un nombre de producto?
    5. ¿Parece una oración completa?
    """
    if not producto:
        return True
    palabras = producto.split()
    if len(palabras) > 4:
        return True
    if any(c.isdigit() for c in producto):
        return True
    # contiene una palabra que es número escrito que no se convirtió
    if any(_quitar_acentos(p.lower()) in NUMEROS_ESCRITOS for p in palabras):
        return True
    # Contiene símbolo monetario (palabra completa; no rechazar "quetzaltecas")
    if re.search(r"[qQ]\s*\d|\bgtq\b|\bquetzales?\b", producto, re.IGNORECASE):
        return True
    # Es demasiado largo (más de 35 caracteres)
    if len(producto) > 35:
        return True
    # Contiene palabras que son claramente contexto, no producto
    palabras_set = {_quitar_acentos(p.lower()) for p in palabras}
    contexto_completo = {"a", "al", "la", "el", "los", "le", "les", "para", "con",
                         "por", "de", "del", "en", "un", "una", "se", "me", "mi"}
    if palabras_set and palabras_set.issubset(contexto_completo):
        return True
    return False


def _calcular_confianza(intencion, op):
    """Estima la confianza (0-1) de una extracción de venta/compra."""
    confianza = 0.0
    if op.get("producto") and not _no_es_producto_valido(op.get("producto")):
        confianza += 0.5
    if op.get("cantidad"):
        confianza += 0.2
    if op.get("precio_unitario"):
        confianza += 0.15
    if op.get("cliente") or op.get("proveedor"):
        confianza += 0.15
    return round(min(confianza, 1.0), 2)


def _validar_compra(operacion):
    errores = []
    if not operacion.get("cantidad"):
        errores.append("Falta la cantidad.")
    if not operacion.get("producto"):
        errores.append("Falta el producto.")
    return errores


def _validar_venta(operacion):
    errores = []
    if not operacion.get("cantidad"):
        errores.append("Falta la cantidad vendida.")
    if not operacion.get("producto"):
        errores.append("Falta el producto.")
    return errores


# ---------------------------------------------------------------------------
# Operaciones no comerciales (gasto, inventario, produccion)
# ---------------------------------------------------------------------------

def _detectar_gasto(original):
    normalizado = _normalizar(original)
    montos = [int(m.group(1)) for m in re.finditer(
        r"(?:q\s*|gtq\s*|quetzales?\s*|gast[eé]\s*|pagu[eé]\s*)?(\d{1,6})\s*(?:quetzales?|pesos)?",
        normalizado, re.IGNORECASE)]
    monto = montos[0] if montos else None
    texto = re.sub(
        r"\b(gast[eé]|gastamos|gastando|pagu[eé]|pague|pagando|comprando|"
        r"q|quetzales?|pesos)\b", " ", normalizado, flags=re.IGNORECASE)
    concepto = _extraer_producto(texto, None, None, None)
    return {"tipo": "gasto", "monto": monto, "concepto": concepto,
            "descripcion": concepto}


def _detectar_inventario(original):
    normalizado = _normalizar(original)
    tokens = normalizado.split()
    cantidad, _ = _extraer_cantidad(normalizado, tokens)
    texto = re.sub(
        r"\b(me quedar?|quedan|tengo|hay|stock|existencia|de|"
        r"agreg(?:ue|u[eé]|amos|ar)|a[nñ]ad(?:i|í|imos|ir)|"
        r"registre|registr[eé]|registrar|al|inventario)\b",
        " ", normalizado, flags=re.IGNORECASE)
    producto = _extraer_producto(texto, None, None, None)
    return {"tipo": "inventario", "producto": producto, "existencia": cantidad,
            "concepto": producto}


def _detectar_ingreso_inventario(original):
    normalizado = _normalizar(original)
    tokens = normalizado.split()
    cantidad, _ = _extraer_cantidad(normalizado, tokens)
    texto = re.sub(
        r"\b(ingresaron|ingres[oó]|entraron|entr[oó]|recibimos|recib[ií]|de|"
        r"agreg(?:ue|u[eé]|amos|ar)|a[nñ]ad(?:i|í|imos|ir)|"
        r"al|inventario)\b",
        " ", normalizado, flags=re.IGNORECASE)
    producto = _extraer_producto(texto, None, None, None)
    return {"tipo": "inventario", "producto": producto, "existencia": cantidad,
            "concepto": producto, "movimiento": "ENTRADA"}


def _detectar_produccion(original):
    normalizado = _normalizar(original)
    tokens = normalizado.split()
    cantidad, _ = _extraer_cantidad(normalizado, tokens)
    texto = re.sub(
        r"\b(fabricamos|fabricaron|fabric[oó]|producimos|produjimos|produje|"
        r"elaboramos|elaboraron|hicimos|hicieron|manufacturamos|"
        r"unidades?|se|de)\b", " ", normalizado, flags=re.IGNORECASE)
    producto = _extraer_producto(texto, None, None, None)
    return {"tipo": "produccion", "producto": producto, "cantidad": cantidad}


# ---------------------------------------------------------------------------
# Conversión a estructura interna + compatibilidad
# ---------------------------------------------------------------------------

def _estructura_interna(intencion, op, mensaje_humano, token):
    """Estructura nueva (sección 3 y 22) + compatibilidad con el formato previo."""
    try:
        cantidad = int(op.get("cantidad") or 0) or None
    except (TypeError, ValueError):
        cantidad = None
    try:
        precio = int(op.get("precio_unitario") or 0) or None
    except (TypeError, ValueError):
        precio = None

    error = op.get("_errores") or []

    # Calcular el total (solo interna para la estructura; el backend lo
    # recalcula al persistir — sección 12).
    total_price = None
    if cantidad is not None and precio is not None:
        total_price = round(cantidad * precio, 2)

    # Compatibilidad: la capa de servicio espera `tipo` dentro de `operacion`
    # (el token de confirmación guarda operacion, no el resultado completo).
    op_guardado = dict(op)
    op_guardado["tipo"] = _intencion_a_tipo(intencion)

    return {
        "interpretado": not error,
        "tipo": _intencion_a_tipo(intencion),
        "intent": intencion,
        "operacion": op_guardado,
        "mensaje_humano": mensaje_humano,
        "token_sesion": token,
        "errores": error,
        "intencion": intencion,
        "estructura": {
            "intent": intencion,
            "product": op.get("producto"),
            "customer": op.get("cliente"),
            "supplier": op.get("proveedor"),
            "quantity": cantidad,
            "unit": op.get("unidad"),
            "unit_price": precio,
            "total_price": total_price,
            "discount": None,
            "payment_method": None,
            "date": None,
            "confidence": op.get("confidence", 0.0),
        },
    }


# ---------------------------------------------------------------------------
# Consultas del asesor virtual
# ---------------------------------------------------------------------------

def _es_saludo(mensaje):
    return bool(SALUDO_RE.match(_normalizar(mensaje).strip()))


def _detectar_consulta(mensaje):
    normalizado = _normalizar(mensaje)
    for intencion, patron in CONSULTA_PATTERNS:
        if patron.search(normalizado):
            return intencion
    return None


def _consulta_de(mensaje):
    if _es_saludo(mensaje):
        return "saludo"
    return _detectar_consulta(mensaje)


def _resultado_consulta(intencion, mensaje):
    return {
        "interpretado": True,
        "consulta": True,
        "tipo": intencion,
        "intencion": intencion,
        "mensaje_humano": mensaje,
        "token_sesion": None,
        "errores": [],
    }


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def interpretar(mensaje, intencion_forzada=None):
    """Convierte un mensaje de lenguaje natural en estructura (API pública).

    Mantiene el formato previo para no romper app.py / service.py / frontend,
    e incluye la nueva estructura interna con intención y confianza.

    `intencion_forzada` se usa en mensajes con varias cláusulas cuando una
    cláusula continua la operación anterior sin repetir el verbo
    (p.ej. '... y 20 sandías a María').
    """
    mensaje = (mensaje or "").strip()
    if not mensaje:
        return {
            "interpretado": False,
            "operacion": None,
            "mensaje": "No se recibió ningún mensaje.",
            "token_sesion": str(uuid.uuid4()),
        }

    consulta = _consulta_de(mensaje)
    if consulta and not intencion_forzada:
        return _resultado_consulta(consulta, mensaje)

    normalizado = _normalizar(mensaje)
    intencion = _detectar_intencion(normalizado) or intencion_forzada

    # Consultas de datos: devolver como consulta para que app.py responda
    # con datos reales del negocio.
    if intencion in ("SALES_QUERY", "PURCHASE_QUERY", "PRODUCT_QUERY", "INVENTORY_QUERY"):
        return _resultado_consulta(_intencion_a_tipo(intencion), mensaje)

    if intencion in ("SALE", "PURCHASE"):
        extraido = _detectar_venta_compra(mensaje, intencion)
        op = dict(extraido)
        # Validar producto falso
        if _no_es_producto_valido(op.get("producto")):
            op["confidence"] = 0.15
            op["producto"] = None
        else:
            op["confidence"] = _calcular_confianza(intencion, op)
        op["_errores"] = _validar_compra(op) if intencion == "PURCHASE" else _validar_venta(op)
        return _estructura_interna(intencion, op, mensaje, str(uuid.uuid4()))

    if intencion == "INVENTORY":
        if re.search(
            r"\b(ingresaron|ingres[oó]|entraron|entr[oó]|recibimos|recib[ií]|"
            r"agreg(?:ue|u[eé]|amos|ar)|a[nñ]ad(?:i|í|imos|ir))\b",
            normalizado,
        ):
            operacion = _detectar_ingreso_inventario(mensaje)
        else:
            operacion = _detectar_inventario(mensaje)
        errores = []
        if operacion.get("existencia") is None:
            errores.append("Falta la existencia registrada.")
        return {
            "interpretado": not errores,
            "tipo": "inventario",
            "intent": "INVENTORY",
            "operacion": operacion,
            "mensaje_humano": mensaje,
            "token_sesion": str(uuid.uuid4()),
            "errores": errores,
        }

    if intencion == "PRODUCTION":
        operacion = _detectar_produccion(mensaje)
        errores = []
        if not operacion.get("cantidad"):
            errores.append("Falta la cantidad producida.")
        if not operacion.get("producto"):
            errores.append("Falta el producto fabricado.")
        return {
            "interpretado": not errores,
            "tipo": "produccion",
            "intent": "PRODUCTION",
            "operacion": operacion,
            "mensaje_humano": mensaje,
            "token_sesion": str(uuid.uuid4()),
            "errores": errores,
        }

    if intencion == "EXPENSE":
        operacion = _detectar_gasto(mensaje)
        errores = []
        if not operacion.get("monto"):
            errores.append("Falta el monto del gasto.")
        return {
            "interpretado": not errores,
            "tipo": "gasto",
            "intent": "EXPENSE",
            "operacion": operacion,
            "mensaje_humano": mensaje,
            "token_sesion": str(uuid.uuid4()),
            "errores": errores,
        }

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


CLAUSULAS_RE = re.compile(r"\s+(?:y\s+|\+\s*|,\s*|;\s*|y\s+tambi[eé]n\s+|"
                          r"adem[aá]s\s+|tambi[eé]n\s+)\s*")


def _dividir_clausulas(mensaje):
    partes = CLAUSULAS_RE.split(mensaje)
    return [p.strip() for p in partes if p.strip()]


def interpretar_multiples(mensaje):
    """Interpreta un mensaje que puede contener varias operaciones.

    Divide el texto en cláusulas y devuelve una lista de resultados. Si el
    mensaje completo es una consulta, devuelve un único resultado consulta.
    """
    texto = (mensaje or "").strip()

    if not texto:
        return [{
            "interpretado": False,
            "operacion": None,
            "mensaje": "No se recibió ningún mensaje.",
            "token_sesion": str(uuid.uuid4()),
        }]

    consulta = _consulta_de(texto)
    if consulta:
        return [_resultado_consulta(consulta, texto)]

    clausulas = _dividir_clausulas(texto)
    resultados = []
    intencion_previa = None
    for clausula in clausulas:
        # Si la cláusula no trae verbo pero está dentro de una cadena de
        # venta/compra, se hereda la intención de la cláusula anterior
        # (patrón conversacional: '... y 20 sandías a María').
        n_clausula = _normalizar(clausula)
        intencion_clausula = _detectar_intencion(n_clausula)
        forzada = None
        if (intencion_clausula is None and intencion_previa in ("SALE", "PURCHASE")):
            forzada = intencion_previa
        if intencion_clausula in ("SALE", "PURCHASE"):
            intencion_previa = intencion_clausula
        resultados.append(interpretar(clausula, intencion_forzada=forzada))

    if len(resultados) > 1:
        con_contenido = [r for r in resultados
                         if not (r.get("consulta") and r.get("tipo") == "saludo")]
        if con_contenido:
            resultados = con_contenido

    return resultados
