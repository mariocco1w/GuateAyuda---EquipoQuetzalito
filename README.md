El siguiente proyecto representa el trabajo realizado por el EquipoQuetzalito que trata de solucionar la problematica de las microempresas en guatemala y fomentarlas a poder ser empresas formarles, la solucion de este es ofrecerles un sistema relacionado a un CRM que les apoye a realizar calculos de sus ventas y realice predicciones automaticas para poder dar una mejor toma de decisiones al empresario.
La estructura utilizada es la siguiente:
                    EMPRESARIO
                         │
                         ▼
                ┌─────────────────┐
                │   FRONTEND WEB  │
                └────────┬────────┘
                         │
             ┌───────────┴───────────┐
             │                       │
             ▼                       ▼
       DASHBOARD                  CHAT IA
             │                       │
             └───────────┬───────────┘
                         ▼
                    API / BACKEND
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
      BASE DATOS    MOTOR ANALÍTICO   MOTOR ML
          │              │              │
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                 RESULTADOS / MÉTRICAS
                         │
                         ▼
                   RECOMENDACIONES

REGLAMENTACION Y LINEAMIENTOS PARA EL DESAROLLO DE GUATEAYUDA
# CONTEXTO MAESTRO — GUATEAYUDA | HACKATHON FIT 2026

## 1. Contexto general

Estamos desarrollando **GuateAyuda** para la Hackathon FIT 2026 — Guatemala 2035, track **PRODUCIR**.

La regla principal del proyecto es:

**Problema primero. Tecnología después.**

La solución debe contribuir principalmente a:

1. aumentar productividad;
2. ampliar acceso a oportunidades;
3. fortalecer decisiones financieras.

Nuestro objetivo principal será **aumentar productividad y mejorar decisiones mediante datos**, dejando el acceso a oportunidades como evolución posterior.

---

# 2. Problema que queremos resolver

Muchos microempresarios conocen bien su negocio y generan información diariamente sobre:

* ventas;
* productos;
* gastos;
* inventario;
* producción;
* disponibilidad.

El problema es que gran parte de esa información queda:

* en memoria;
* en papel;
* en mensajes;
* en registros informales;
* o en herramientas que no convierten los datos en información útil.

El problema NO es simplemente que “no sepan administrar”.

Nuestro insight es:

**El microempresario ya posee conocimiento de su negocio. Lo que necesita es una forma sencilla de transformar ese conocimiento y actividad cotidiana en información estructurada que le permita entender mejor su negocio y abrir nuevas oportunidades.**

---

# 3. Usuario principal del MVP

No diseñar para empresas grandes.

El MVP está enfocado en:

**Dueño de una microempresa que administra directamente su negocio, usa regularmente un teléfono y no cuenta con un ERP o sistema administrativo formal.**

Ejemplo utilizado para la demo:

**María**, propietaria de un pequeño comedor.

Ella:

* conoce sus productos;
* sabe aproximadamente cuánto vende;
* registra algunas cosas y otras las recuerda;
* utiliza su teléfono;
* no quiere aprender un ERP complejo;
* necesita información comprensible, no términos técnicos.

---

# 4. Idea central de GuateAyuda

GuateAyuda será una infraestructura digital sencilla que permita registrar la actividad cotidiana de una microempresa mediante lenguaje natural.

Ejemplo:

Usuario:

“Vendí 8 almuerzos a Q25.”

GuateAyuda interpreta:

* Tipo: Venta
* Producto: Almuerzo
* Cantidad: 8
* Precio: Q25
* Total: Q200

Luego solicita confirmación.

Al confirmar:

1. se guarda la información;
2. se actualiza el historial;
3. cambia el dashboard;
4. se actualizan indicadores;
5. progresivamente se construye el **Perfil Productivo Digital** del negocio.

La propuesta puede resumirse así:

**Actividad cotidiana → datos → historial → información → Perfil Productivo Digital → mejores decisiones → oportunidades futuras.**

---

# 5. Qué NO es GuateAyuda

No queremos construir:

* un chatbot genérico;
* un mini ERP completo;
* un sistema contable;
* una aplicación bancaria;
* un marketplace;
* un sistema SAT;
* un asesor que solo dé respuestas generales;
* IA utilizada únicamente porque “se ve innovadora”.

El elemento conversacional es únicamente una forma sencilla de capturar información.

---

# 6. Papel de WhatsApp

WhatsApp se considera un **canal de interacción**, no el producto completo.

Visión:

Microempresario
→ WhatsApp
→ GuateAyuda
→ datos estructurados
→ dashboard
→ Perfil Productivo Digital.

Sin embargo, para reducir riesgos en el MVP:

Primero debe funcionar una interfaz web conversacional.

Después, si hay tiempo, se conecta ese mismo backend con WhatsApp.

La aplicación web debe seguir funcionando aunque falle la API de WhatsApp durante la demo.

---

# 7. MVP oficial del equipo

El MVP debe demostrar solamente este flujo:

1. Usuario entra a GuateAyuda.
2. Visualiza su negocio.
3. Escribe una operación cotidiana.
4. El sistema interpreta el mensaje.
5. Presenta la información detectada.
6. Usuario confirma.
7. Backend guarda la operación.
8. Dashboard se actualiza.
9. Se muestra un resultado útil.

Ejemplo:

“Vendí 8 almuerzos a Q25.”

↓

Interpretación

↓

8 × Q25 = Q200

↓

Confirmación

↓

Base de datos

↓

Dashboard pasa de:

Q1,050

a:

Q1,250

↓

GuateAyuda identifica nueva información sobre la actividad del negocio.

Este flujo es la prioridad absoluta.

---

# 8. Operaciones del MVP

El sistema debe entender inicialmente solamente tres tipos.

## Venta

Ejemplo:

“Vendí 5 cafés a Q12.”

Resultado:

tipo = venta
producto = café
cantidad = 5
precio_unitario = 12
total = 60

## Gasto

Ejemplo:

“Gasté Q150 comprando verduras.”

Resultado:

tipo = gasto
concepto = verduras
monto = 150

## Inventario

Ejemplo:

“Me quedan 10 gaseosas.”

Resultado:

tipo = inventario
producto = gaseosa
existencia = 10

No agregar más operaciones hasta que estas funcionen correctamente.

---

# 9. Pantallas del MVP

## Pantalla 1 — Inicio

Mostrar:

* nombre del negocio;
* propietario;
* actividad;
* acceso al dashboard.

Ejemplo:

Comedor Doña María

## Pantalla 2 — Dashboard

Indicadores principales:

* ventas registradas;
* gastos registrados;
* número de operaciones;
* productos activos.

También puede mostrar:

* ventas por día;
* productos de mayor movimiento;
* actividad reciente;
* inventario bajo;
* registros recientes.

IMPORTANTE:

No llamar “ganancia” a ventas menos gastos si no contamos con costo de ventas y demás componentes necesarios.

## Pantalla 3 — GuateAyuda

Interfaz conversacional.

Ejemplo:

GuateAyuda:
¿Qué ocurrió hoy en tu negocio?

Usuario:
Vendí 8 almuerzos a Q25.

GuateAyuda:
Detecté:

Producto: Almuerzo
Cantidad: 8
Precio unitario: Q25
Total: Q200

[Confirmar] [Corregir]

---

# 10. Perfil Productivo Digital

Es uno de los principales diferenciadores de GuateAyuda.

Debe crecer conforme el usuario registra información.

Ejemplo:

Perfil Productivo Digital

Negocio:
Comedor Doña María

Actividad:
Venta de alimentos

Productos activos:
7

Días con actividad registrada:
22

Operaciones:
186

Información disponible:

Ventas ✓
Gastos ✓
Productos ✓
Inventario ✓
Producción —

El MVP NO debe afirmar que este perfil está “verificado” por terceros.

Por ahora es:

**Perfil Productivo Digital trazable construido con la actividad registrada por el negocio.**

En el futuro podría utilizarse, con autorización del propietario, para acceder a:

* capacitación;
* proveedores;
* nuevos mercados;
* financiamiento;
* servicios empresariales.

---

# 11. Arquitectura técnica propuesta

Stack recomendado:

* Python
* Flask
* PostgreSQL
* HTML
* Bootstrap
* JavaScript
* Chart.js
* API de modelo de lenguaje

Arquitectura:

Usuario
↓
Frontend web
↓
Chat / Dashboard
↓
Backend API
↓
Base de datos
↓
Motor analítico
↓
Indicadores y recomendaciones

El mismo backend posteriormente podrá recibir mensajes desde WhatsApp.

---

# 12. Responsabilidad de la IA

La IA tendrá inicialmente UNA responsabilidad principal:

**Convertir lenguaje cotidiano en información estructurada.**

Ejemplo:

“Hoy vendí diez panes con pollo a quince quetzales cada uno.”

↓

{
tipo: venta,
producto: pan con pollo,
cantidad: 10,
precio_unitario: 15
}

La IA NO debe encargarse de:

* cálculos financieros críticos;
* sumar totales;
* validar saldos;
* modificar directamente datos;
* generar métricas sin evidencia.

Python y las reglas de negocio deben calcular los resultados.

---

# 13. Machine Learning

NO implementar Machine Learning predictivo en el MVP.

No tenemos todavía suficiente historial real para justificar:

* predicción de ventas;
* predicción de demanda;
* scoring;
* modelos financieros.

En el MVP utilizaremos:

**datos + reglas analíticas.**

Ejemplos:

Si inventario <= mínimo:
“Inventario bajo.”

Si producto A tiene más ventas:
“Producto con mayor movimiento.”

Si ventas actuales > período anterior:
“Las ventas registradas aumentaron X%.”

Machine Learning queda como evolución futura cuando exista volumen suficiente de datos reales.

---

# 14. Base de datos mínima

Tablas sugeridas:

## negocio

* id
* nombre
* actividad
* ubicación

## producto

* id
* negocio_id
* nombre
* precio
* existencia

## transaccion

* id
* negocio_id
* tipo
* fecha
* descripción
* monto

## detalle_venta

* id
* transaccion_id
* producto_id
* cantidad
* precio_unitario
* subtotal

## interaccion

* id
* negocio_id
* mensaje_original
* tipo_detectado
* datos_extraidos
* confirmado
* fecha

La tabla interacción permite demostrar:

Mensaje humano
→ interpretación
→ estructura
→ confirmación
→ dato persistente.

---

# 15. Datos demo

Crear aproximadamente 8 negocios ficticios para pruebas.

Ejemplos:

* Comedor Doña María
* Café Chapín
* Panadería Lupita
* Tienda El Quetzal
* Artesanías Maya
* Frutas Don José
* Textiles Ana
* Dulces Chapines

Pero durante el pitch mostrar solamente UN caso principal.

Los demás sirven para:

* pruebas;
* poblar base de datos;
* gráficas;
* demostrar escalabilidad estructural.

Los datos simulados deben estar claramente identificados como datos demo.

---

# 16. Validación

No confundir usuarios simulados con usuarios reales.

Un LLM puede servir para:

* probar escenarios;
* encontrar casos límite;
* criticar UX;
* generar datos demo.

Pero NO debe presentarse como validación real.

Intentar probar el prototipo con al menos 2 o 3 personas reales.

Preguntar:

1. ¿Entiende qué debe hacer?
2. ¿Entiende qué información detectó GuateAyuda?
3. ¿Le parece útil el resultado?
4. ¿Qué parte le confunde?
5. ¿Usaría esta forma de registrar información?

Guardar evidencia del feedback.

---

# 17. Orden correcto de desarrollo

No comenzar por IA.

Orden:

1. Crear estructura del proyecto.
2. Crear PostgreSQL.
3. Crear datos demo.
4. Crear dashboard leyendo PostgreSQL.
5. Crear formulario manual de venta.
6. Guardar operación.
7. Actualizar dashboard.
8. Crear interfaz conversacional.
9. Integrar interpretación IA.
10. Agregar gastos.
11. Agregar inventario.
12. Agregar reglas analíticas.
13. Probar.
14. Si queda tiempo, integrar WhatsApp.

Primero debe funcionar:

PostgreSQL
→ Backend
→ Dashboard.

Después:

Texto
→ IA
→ estructura
→ confirmación
→ mismo backend.

---

# 18. Prioridades

## P0 — obligatorio

* negocio demo;
* productos;
* registro de venta;
* confirmación;
* almacenamiento PostgreSQL;
* dashboard;
* actualización automática;
* resultado útil.

## P1 — deseable

* gastos;
* inventario;
* interpretación LLM;
* Perfil Productivo Digital;
* reglas y alertas.

## P2 — solo si queda tiempo

* WhatsApp real;
* recomendaciones adicionales;
* UX avanzada.

## Futuro

* Machine Learning;
* modelos predictivos;
* créditos;
* marketplace;
* integración bancaria;
* SAT;
* proveedores;
* mercados externos.

---

# 19. Demo narrativa

El pitch debe demostrar transformación.

ANTES:

María administra su comedor y conoce su negocio, pero parte de la información queda dispersa.

DURANTE:

Escribe:

“Vendí 8 almuerzos a Q25.”

GuateAyuda interpreta:

8 almuerzos
Q25 cada uno
Q200 total

María confirma.

DESPUÉS:

El dashboard cambia.

La venta queda registrada.

El Perfil Productivo Digital incorpora nueva información.

RESULTADO:

Una actividad cotidiana que antes quedaba en memoria o registros dispersos ahora se convierte en información estructurada y útil.

---

# 20. Impacto del MVP

No afirmar todavía:

“GuateAyuda aumentó las ventas X%.”

No tenemos evidencia suficiente.

Medidas iniciales defendibles:

* operaciones registradas;
* porcentaje de mensajes correctamente interpretados;
* tiempo requerido para registrar una operación;
* cantidad de información estructurada generada;
* usuarios que completan el flujo;
* comprensión del dashboard;
* utilidad percibida.

Más adelante se podrá medir:

* reducción de tiempo administrativo;
* mejora en control;
* reducción de pérdidas;
* crecimiento de ventas;
* acceso a nuevos clientes;
* acceso a financiamiento.

---

# 21. Escalabilidad hacia 2035

No escalar primero hacia empresas grandes.

Ruta propuesta:

2026:
Piloto con microempresas.

↓

2027–2029:
Más actividades económicas.

↓

2030–2032:
Expansión urbana y rural.

↓

2033–2035:
Red de Perfiles Productivos Digitales.

↓

Con autorización del empresario:

* mercados;
* capacitación;
* proveedores;
* servicios financieros;
* oportunidades empresariales.

La ventaja de GuateAyuda puede estar precisamente en atender negocios demasiado pequeños para utilizar un ERP tradicional.

---

# 22. Criterios de la Hackathon

Toda decisión debe evaluarse considerando:

* Relevancia y alineación — 20%
* Impacto — 20%
* Innovación — 20%
* Uso estratégico de tecnología — 20%
* Viabilidad y escalabilidad — 20%

La tecnología debe ser necesaria.

Pregunta de control:

**Si quitamos la tecnología, ¿la solución pierde una función esencial?**

En GuateAyuda sí:

sin procesamiento digital no podemos transformar lenguaje cotidiano en datos estructurados, generar historial, indicadores ni construir progresivamente el Perfil Productivo Digital.

---

# 23. Riesgos que debemos evitar

No agregar funcionalidades por entusiasmo.

No inventar estadísticas.

No afirmar que datos simulados son reales.

No utilizar IA para cálculos críticos.

No llamar “predicción” a una simple regla.

No afirmar que el Perfil Productivo está verificado externamente.

No depender completamente de WhatsApp para la demo.

No construir módulos que no aporten al flujo principal.

No convertir GuateAyuda en un ERP.

---

# 24. Regla para cualquier IA que trabaje en el proyecto

Antes de proponer o desarrollar algo, verificar:

1. ¿Ayuda al usuario principal?
2. ¿Resuelve el problema definido?
3. ¿Forma parte del flujo principal?
4. ¿Es necesario para demostrar el MVP?
5. ¿Puede implementarse dentro del tiempo?
6. ¿Se puede demostrar frente al jurado?
7. ¿Genera evidencia?

Si la respuesta es no, clasificarlo como futuro y NO incorporarlo al MVP.

No modificar el alcance del proyecto sin justificar claramente el cambio.

Cuando falte información:

* no inventar;
* indicar que es hipótesis;
* proponer cómo validarla.

---

# 25. Objetivo inmediato del equipo

Antes de construir cualquier funcionalidad avanzada, lograr este escenario completamente funcional:

**“Vendí 8 almuerzos a Q25”**

↓

GuateAyuda interpreta

↓

Usuario confirma

↓

Se guarda Q200 como venta

↓

PostgreSQL registra la operación

↓

Dashboard aumenta Q200

↓

Actividad reciente muestra la venta

↓

Perfil Productivo Digital se actualiza.

Cuando este recorrido funcione de principio a fin, el MVP base estará demostrado.

A partir de ahí se puede ampliar sin romper el flujo principal.