/* LÓGICA EMPRESARIAL - GUATEAYUDA */

document.addEventListener("DOMContentLoaded", () => {
    console.log("Sistema Empresarial iniciado.");

    const metaNegocioId = document.querySelector('meta[name="negocio-id"]');
    const negocioId = metaNegocioId ? metaNegocioId.content : null;

    if (!negocioId) {
        console.log("No se encontró negocioId en la sesión.");
        return;
    }

    // Cargar Dashboard
    const dashboardKPIs = document.getElementById("kpi-ventas");
    if (dashboardKPIs) {
        cargarDashboard(negocioId);
        cargarInteligencia(negocioId);
    }

    function _panelOk(contenedor, mensaje) {
        contenedor.innerHTML = `<p class="ok-message"><i class="fa-solid fa-circle-check"></i> ${_esc(mensaje)}</p>`;
    }

    function _panelError(contenedor, mensaje) {
        contenedor.innerHTML = `<p>${_esc(mensaje || "No se pudieron cargar los datos.")}</p>`;
    }

    function cargarInteligencia(negocioId) {
        // Predicción de ventas (7 días)
        fetch(`/api/negocio/${negocioId}/prediccion?dias=7`)
            .then(res => res.json())
            .then(data => {
                const contenedor = document.getElementById("lista-prediccion");
                if (!contenedor) return;
                if (!data.disponible) {
                    _panelOk(contenedor, data.mensaje || "Sin historial suficiente para predecir.");
                    return;
                }
                const total = (data.predicciones || []).reduce((s, p) => s + Number(p.estimado || 0), 0);
                const estado = data.estado === "modelo_ml" ? "Modelo ML"
                             : data.estado === "mixto" ? "Mixto"
                             : "Promedio histórico";
                const filas = (data.predicciones || []).map(p =>
                    `<div class="panel-row"><strong>${_esc(p.dia)}</strong><span>Q${Number(p.estimado || 0).toLocaleString()}</span></div>`
                ).join("");
                contenedor.innerHTML =
                    `<div class="panel-meta"><span class="stock-tag">${_esc(estado)}</span>` +
                    `<span>Próximos ${data.periodo_dias} días: <b>Q${total.toLocaleString()}</b></span></div>` + filas;
            })
            .catch(err => {
                console.error("Error predicción:", err);
                const contenedor = document.getElementById("lista-prediccion");
                if (contenedor) _panelError(contenedor, "No se pudo generar la predicción.");
            });

        // Riesgo de inventario (demanda estimada)
        fetch(`/api/negocio/${negocioId}/inventario-predictivo?dias=7`)
            .then(res => res.json())
            .then(data => {
                const contenedor = document.getElementById("lista-inventario-riesgo");
                if (!contenedor) return;
                const enRiesgo = data.en_riesgo || [];
                if (!enRiesgo.length) {
                    _panelOk(contenedor, "Sin productos en riesgo en los próximos días.");
                    return;
                }
                contenedor.innerHTML = enRiesgo.map(p => {
                    const dias = p.dias_hasta_agotamiento !== null && p.dias_hasta_agotamiento !== undefined
                        ? `${p.dias_hasta_agotamiento} días` : "stock bajo";
                    let html = `<div class="panel-row"><strong>${_esc(p.producto)}</strong>` +
                        `<span class="stock-tag">${_esc(dias)}</span></div>`;
                    if (p.reposicion_sugerida) {
                        html += `<div class="panel-sub">Sugerencia: reponer ≈ ${p.reposicion_sugerida} u. (estima ${p.consumo_diario}/día). Decides tú.</div>`;
                    }
                    return html;
                }).join("");
            })
            .catch(err => {
                console.error("Error inventario predictivo:", err);
                const contenedor = document.getElementById("lista-inventario-riesgo");
                if (contenedor) _panelError(contenedor, "No se pudo analizar el inventario.");
            });

        // Anomalías detectadas
        fetch(`/api/negocio/${negocioId}/anomalias?dias=60`)
            .then(res => res.json())
            .then(data => {
                const contenedor = document.getElementById("lista-anomalias");
                if (!contenedor) return;
                const areas = data.areas || {};
                const todas = Object.keys(areas)
                    .filter(k => areas[k].anomalias)
                    .flatMap(k => areas[k].anomalias.map(a => ({ ...a, area: k })));
                if (!data.disponible || todas.length === 0) {
                    _panelOk(contenedor, data.mensaje || "Sin comportamientos inusuales en el periodo revisado.");
                    return;
                }
                contenedor.innerHTML = todas.slice(0, 5).map(a => {
                    const signo = a.direccion === "alta" ? "+" : "−";
                    const etiqueta = a.area.charAt(0).toUpperCase() + a.area.slice(1);
                    return `<div class="panel-row"><strong>${_esc(etiqueta)} · ${_esc(a.fecha)}</strong>` +
                        `<span class="stock-tag">${signo}${Number(a.desviacion_porcentual || 0).toFixed(1)}%</span></div>` +
                        `<div class="panel-sub">Requiere revisión.</div>`;
                }).join("");
            })
            .catch(err => {
                console.error("Error anomalías:", err);
                const contenedor = document.getElementById("lista-anomalias");
                if (contenedor) _panelError(contenedor, "No se pudieron detectar anomalías.");
            });

        // Recomendaciones accionables
        fetch(`/api/negocio/${negocioId}/recomendaciones?dias=7`)
            .then(res => res.json())
            .then(data => {
                const contenedor = document.getElementById("lista-recomendaciones");
                if (!contenedor) return;
                const items = data.recomendaciones || [];
                if (!items.length) {
                    _panelOk(contenedor, "Todo se ve dentro del patrón habitual del negocio.");
                    return;
                }
                const clase = { "ALTA": "badge-alta", "MEDIA": "badge-media", "BAJA": "badge-baja" };
                contenedor.innerHTML = items.map(r =>
                    `<div class="reco-item">` +
                    `<div class="reco-head"><span class="stock-tag ${clase[r.prioridad] || ""}">${_esc(r.prioridad)}</span>` +
                    `<strong>${_esc(r.titulo)}</strong></div>` +
                    `<div class="reco-desc">${_esc(r.accion_sugerida)}</div>` +
                    `</div>`).join("");
            })
            .catch(err => {
                console.error("Error recomendaciones:", err);
                const contenedor = document.getElementById("lista-recomendaciones");
                if (contenedor) _panelError(contenedor, "No se pudieron generar recomendaciones.");
            });
    }

    function cargarDashboard(negocioId) {
        fetch(`/api/negocio/${negocioId}/dashboard`)
            .then(res => res.json())
            .then(data => {
                if (data.ventas_registradas !== undefined) {
                    document.getElementById("kpi-ventas").textContent = `Q${data.ventas_registradas.toLocaleString()}`;
                    document.getElementById("kpi-gastos").textContent = `Q${data.gastos_registrados.toLocaleString()}`;
                    document.getElementById("kpi-operaciones").textContent = data.numero_operaciones;
                    document.getElementById("kpi-productos").textContent = data.productos_activos;
                }
            })
            .catch(err => console.error("Error cargando dashboard:", err));

        fetch(`/api/negocio/${negocioId}/inventario-bajo`)
            .then(res => res.json())
            .then(data => {
                const contenedor = document.getElementById("lista-inventario-bajo");
                const items = data.inventario_bajo || [];
                if (contenedor) {
                    if (items.length === 0) {
                        contenedor.innerHTML = "<p class='ok-message'><i class='fa-solid fa-circle-check'></i> Todo el inventario está en niveles óptimos.</p>";
                    } else {
                        contenedor.innerHTML = items.map(i => `<div class="panel-row"><strong>${i.producto}</strong><span class="stock-tag">${i.existencia} disp · mín ${i.minimo}</span></div>`).join("");
                    }
                }
            })
            .catch(err => console.error("Error inventario bajo:", err));

        fetch(`/api/negocio/${negocioId}/top-productos?n=3`)
            .then(res => res.json())
            .then(data => {
                const contenedor = document.getElementById("lista-top-productos");
                const items = data.top_productos || [];
                if (contenedor) {
                    if (items.length === 0) {
                        contenedor.innerHTML = "<p>Sin ventas registradas aún.</p>";
                    } else {
                        contenedor.innerHTML = items.map(p => `<div class="panel-row"><strong>${p.producto}</strong><span>${p.unidades} un · Q${p.ingresos.toLocaleString()}</span></div>`).join("");
                    }
                }
            })
            .catch(err => console.error("Error top productos:", err));
    }

    // ------------------------------------------------------------------
    // Asesor Virtual - conversación por burbujas
    // ------------------------------------------------------------------
    let tokensSesion = [];
    let mensajesHumanos = [];
    let bubbleOperacion = null;

    const chatConversacion = document.getElementById("chat-conversacion");
    const btnEnviar = document.getElementById("btn-enviar-chat");
    const inputMensaje = document.getElementById("chat-mensaje");

    function _esc(texto) {
        const s = String(texto === null || texto === undefined ? "" : texto);
        const mapa = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
        return s.replace(/[&<>"']/g, c => mapa[c]);
    }

    function _append(html) {
        const div = document.createElement("div");
        div.innerHTML = html;
        const nodo = div.firstElementChild;
        chatConversacion.appendChild(nodo);
        chatConversacion.scrollTop = chatConversacion.scrollHeight;
        return nodo;
    }

    function _burbujaUsuario(mensaje) {
        _append(`<div class="chat-msg msg-user">${_esc(mensaje)}</div>`);
    }

    function _burbujaPensando() {
        _append(`<div class="chat-msg msg-bot chat-typing" id="chat-pensando">`
            + `<span class="dot"></span><span class="dot"></span><span class="dot"></span>`
            + `&nbsp; Pensando...</div>`);
    }

    function _quitarPensando() {
        const n = document.getElementById("chat-pensando");
        if (n) n.remove();
    }

    function _descripcionOperacion(op) {
        // Devuelve una línea legible con el detalle de una operación detectada.
        const t = op.operacion;
        if (op.tipo === "venta") {
            let d = `<i class="fa-solid fa-cash-register" style="color:var(--green);"></i> Venta · ${_esc(t.producto)} × ${t.cantidad}`;
            if (t.cliente) d += ` a ${_esc(t.cliente)}`;
            if (t.precio_unitario) d += ` a Q${t.precio_unitario}`;
            return d;
        } else if (op.tipo === "compra") {
            let d = `<i class="fa-solid fa-cart-shopping" style="color:#1565C0;"></i> Compra · ${_esc(t.producto)} × ${t.cantidad}`;
            if (t.proveedor) d += ` a ${_esc(t.proveedor)}`;
            if (t.precio_unitario) d += ` a Q${t.precio_unitario}`;
            return d;
        } else if (op.tipo === "gasto") {
            return `<i class="fa-solid fa-receipt" style="color:#cc0000;"></i> Gasto · ${_esc(t.concepto || t.descripcion || "gasto")} por Q${t.monto}`;
        } else if (op.tipo === "inventario") {
            return `<i class="fa-solid fa-boxes-stacked" style="color:var(--blue-main);"></i> Inventario · ${_esc(t.producto)} (${t.existencia} u.)`;
        } else if (op.tipo === "produccion") {
            return `<i class="fa-solid fa-industry" style="color:var(--blue-dark);"></i> Producción · ${t.cantidad} u. de ${_esc(t.producto)}`;
        }
        return `Operación · ${op.tipo}`;
    }

    function _burbujaConsulta(body) {
        let html = `<p class="consulta-mensaje">${_esc(body.mensaje)}</p>`;
        const datos = body.datos || [];
        if (datos.length > 0 && datos[0].producto !== undefined) {
            const filas = datos.map(d =>
                `<div class="consulta-item">`
                + `<span class="c-nombre">${_esc(d.producto)}</span>`
                + `<span class="c-meta">Q${Number(d.precio || 0).toLocaleString()} · ${Number(d.existencia || 0)} disp · mín ${Number(d.minimo || 0)}</span>`
                + `</div>`).join("");
            html += `<div class="consulta-lista">${filas}</div>`;
        } else if (datos.length > 0 && datos[0].etiqueta !== undefined) {
            const filas = datos.map(d =>
                `<div class="consulta-item"><span class="c-nombre">${_esc(d.etiqueta)}</span>`
                + `<span class="c-meta">${_esc(d.valor)}</span></div>`).join("");
            html += `<div class="consulta-lista">${filas}</div>`;
        }
        _append(`<div class="chat-msg msg-bot">${html}</div>`);
    }

    function _burbujaOperacion(body) {
        const operaciones = body.operaciones || [{
            token_sesion: body.token_sesion,
            tipo: body.tipo,
            operacion: body.operacion,
            mensaje_humano: body.mensaje_humano,
        }];

        tokensSesion = operaciones.map(o => o.token_sesion);
        mensajesHumanos = operaciones.map(o => o.mensaje_humano);

        const rowsHtml = operaciones.map((op, idx) => {
            const resumen = (op.resumen || body.resumen);
            const texto = (typeof resumen === "string" && resumen) ? resumen : _descripcionOperacion(op);
            return `<div class="op-row">${_esc(texto)}</div>`;
        }).join("");
        let extra = "";
        if ((body.multiples || operaciones.length > 1)) {
            extra = `<div style="padding-top:8px;color:#5B7076;"><i class="fa-solid fa-info-circle"></i> Se detectaron ${operaciones.length} operaciones.</div>`;
        }

        const nodo = _append(`
            <div class="chat-msg msg-bot">
                <p class="consulta-mensaje">Detecté la información. ¿Confirmas que es correcta?</p>
                <div class="op-list">${rowsHtml}</div>
                ${extra}
                <div class="chat-actions">
                    <button class="btn-confirm" id="btn-confirmar"><i class="fa-solid fa-check"></i> Confirmar</button>
                    <button class="btn-correct" id="btn-corregir"><i class="fa-solid fa-pen"></i> Corregir</button>
                </div>
            </div>`);

        bubbleOperacion = nodo;

        nodo.querySelector("#btn-confirmar").addEventListener("click", confirmarOperaciones);
        nodo.querySelector("#btn-corregir").addEventListener("click", () => {
            nodo.remove();
            bubbleOperacion = null;
            tokensSesion = [];
            mensajesHumanos = [];
            _append(`<div class="chat-msg msg-bot">Por favor, escribe el mensaje corregido.</div>`);
            inputMensaje.focus();
        });
    }

    function confirmarOperaciones() {
        if (tokensSesion.length === 0) return;

        _burbujaPensando();
        const peticiones = tokensSesion.map((token, i) => {
            return fetch(`/api/negocio/${negocioId}/operacion`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token_sesion: token, mensaje_humano: mensajesHumanos[i] || "" })
            }).then(res => res.json());
        });

        Promise.all(peticiones)
        .then(respuestas => {
            _quitarPensando();
            const fallidas = respuestas.filter(r => !r.guardado);
            if (fallidas.length === 0) {
                if (bubbleOperacion) bubbleOperacion.remove();
                bubbleOperacion = null;
                tokensSesion = [];
                mensajesHumanos = [];
                inputMensaje.value = "";
                _append(`<div class="chat-msg msg-bot"><i class="fa-solid fa-circle-check" style="color:var(--green);"></i> ¡Operación(es) guardada(s) con éxito! El dashboard se actualizará.</div>`);
            } else {
                const detalle = fallidas
                    .map(r => r.mensaje || r.error || "operación inválida")
                    .filter(Boolean)
                    .join(" · ");
                _append(`<div class="chat-msg msg-bot">No se pudo guardar: ${_esc(detalle)}. Revisa los datos (por ejemplo, en ventas indica el precio) e inténtalo de nuevo.</div>`);
            }
        })
        .catch(err => {
            console.error(err);
            _quitarPensando();
            _append(`<div class="chat-msg msg-bot">Error al confirmar operaciones.</div>`);
        });
    }

    function enviarChat() {
        const mensaje = inputMensaje.value.trim();
        if (!mensaje) return;

        _burbujaUsuario(mensaje);
        inputMensaje.value = "";

        if (bubbleOperacion) {
            bubbleOperacion.remove();
            bubbleOperacion = null;
        }
        tokensSesion = [];
        mensajesHumanos = [];
        _burbujaPensando();

        fetch(`/api/negocio/${negocioId}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mensaje })
        })
        .then(res => res.json().then(data => ({ status: res.status, body: data })))
        .then(({ status, body }) => {
            _quitarPensando();

            if (body.consulta) {
                _burbujaConsulta(body);
            } else if (status === 200 && body.interpretado) {
                _burbujaOperacion(body);
            } else {
                _append(`<div class="chat-msg msg-bot">${_esc(body.mensaje || "No pude interpretar la operación.")}</div>`);
            }
        })
        .catch(err => {
            console.error(err);
            _quitarPensando();
            _append(`<div class="chat-msg msg-bot">Error de conexión con el servidor.</div>`);
        });
    }

    if (btnEnviar && inputMensaje) {
        btnEnviar.addEventListener("click", enviarChat);
        inputMensaje.addEventListener("keypress", (e) => {
            if (e.key === "Enter") enviarChat();
        });
    }
});