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
            return `<i class="fa-solid fa-cash-register" style="color:var(--green);"></i> Venta · ${_esc(t.producto)} × ${t.cantidad} a Q${t.precio_unitario}`;
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

        const rowsHtml = operaciones.map(op =>
            `<div class="op-row">${_descripcionOperacion(op)}</div>`).join("");
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
                _append(`<div class="chat-msg msg-bot">Algunas operaciones no se guardaron. Revisa e inténtalo de nuevo.</div>`);
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