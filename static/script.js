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
                        contenedor.innerHTML = "<p style='color: #3A8F5B;'>Todo el inventario está en niveles óptimos.</p>";
                    } else {
                        contenedor.innerHTML = items.map(i => `<div style='padding: 6px 0; border-bottom: 1px solid #F0F6F7;'><strong>${i.producto}</strong>: ${i.existencia} en existencia (Mín: ${i.minimo})</div>`).join("");
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
                        contenedor.innerHTML = items.map(p => `<div style='padding: 6px 0; border-bottom: 1px solid #F0F6F7;'><strong>${p.producto}</strong> — ${p.unidades} un. (Q${p.ingresos.toLocaleString()})</div>`).join("");
                    }
                }
            })
            .catch(err => console.error("Error top productos:", err));
    }

    // Chat IA Lógica
    let tokensSesion = [];
    let mensajesHumanos = [];

    const btnEnviar = document.getElementById("btn-enviar-chat");
    const inputMensaje = document.getElementById("chat-mensaje");
    const resultadoContainer = document.getElementById("chat-resultado-container");
    const chatDetalles = document.getElementById("chat-detalles");
    const chatStatus = document.getElementById("chat-status");
    const btnConfirmar = document.getElementById("btn-confirmar");
    const btnCorregir = document.getElementById("btn-corregir");

    if (btnEnviar) {
        btnEnviar.addEventListener("click", enviarChat);
        inputMensaje.addEventListener("keypress", (e) => {
            if (e.key === "Enter") enviarChat();
        });
    }

    function _descripcionOperacion(op) {
        // Devuelve una línea legible con el detalle de una operación detectada.
        const t = op.operacion;
        if (op.tipo === "venta") {
            return `Venta · ${t.producto} × ${t.cantidad} a Q${t.precio_unitario}`;
        } else if (op.tipo === "gasto") {
            return `Gasto · ${t.concepto || t.descripcion || "gasto"} por Q${t.monto}`;
        } else if (op.tipo === "inventario") {
            return `Inventario · ${t.producto} (${t.existencia} u.)`;
        } else if (op.tipo === "produccion") {
            return `Producción · ${t.cantidad} u. de ${t.producto}`;
        }
        return `Operación · ${op.tipo}`;
    }

    function enviarChat() {
        const mensaje = inputMensaje.value.trim();
        if (!mensaje) return;

        chatStatus.textContent = "Interpretando mensaje...";
        resultadoContainer.style.display = "none";

        fetch(`/api/negocio/${negocioId}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mensaje })
        })
        .then(res => res.json().then(data => ({ status: res.status, body: data })))
        .then(({ status, body }) => {
            if (status === 200 && body.interpretado) {
                // Normalizar a lista de operaciones (compatibilidad con la
                // forma simple y la forma múltiple).
                const operaciones = body.operaciones || [{
                    token_sesion: body.token_sesion,
                    tipo: body.tipo,
                    operacion: body.operacion,
                    mensaje_humano: body.mensaje_humano,
                }];

                tokensSesion = operaciones.map(o => o.token_sesion);
                mensajesHumanos = operaciones.map(o => o.mensaje_humano);

                let detalleHtml = "";
                operaciones.forEach((op) => {
                    detalleHtml += `<div style="padding: 8px 0; border-bottom: 1px solid #F0F6F7;">${_descripcionOperacion(op)}</div>`;
                });
                if ((body.multiples || operaciones.length > 1)) {
                    detalleHtml += `<div style="padding-top: 8px; color: #5B7076;">Se detectaron ${operaciones.length} operaciones.</div>`;
                }

                chatDetalles.innerHTML = detalleHtml;
                resultadoContainer.style.display = "block";
                chatStatus.textContent = "";
            } else {
                chatStatus.textContent = body.mensaje || "No se pudo interpretar la operación.";
            }
        })
        .catch(err => {
            console.error(err);
            chatStatus.textContent = "Error de conexión con el servidor.";
        });
    }

    if (btnConfirmar) {
        btnConfirmar.addEventListener("click", () => {
            if (tokensSesion.length === 0) return;

            chatStatus.textContent = "Guardando operaciones...";
            const peticiones = tokensSesion.map((token, i) => {
                return fetch(`/api/negocio/${negocioId}/operacion`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ token_sesion: token, mensaje_humano: mensajesHumanos[i] || "" })
                }).then(res => res.json());
            });

            Promise.all(peticiones)
            .then(respuestas => {
                const fallidas = respuestas.filter(r => !r.guardado);
                if (fallidas.length === 0) {
                    chatStatus.innerHTML = "<span style='color: #3A8F5B; font-weight: bold;'>¡Operaciones guardadas con éxito!</span>";
                    resultadoContainer.style.display = "none";
                    inputMensaje.value = "";
                    tokensSesion = [];
                    mensajesHumanos = [];
                } else {
                    chatStatus.textContent = "Algunas operaciones no se guardaron. Revisa e inténtalo de nuevo.";
                }
            })
            .catch(err => {
                console.error(err);
                chatStatus.textContent = "Error al confirmar operaciones.";
            });
        });
    }

    if (btnCorregir) {
        btnCorregir.addEventListener("click", () => {
            resultadoContainer.style.display = "none";
            chatStatus.textContent = "Por favor, escribe el mensaje corregido.";
            inputMensaje.focus();
        });
    }
});
