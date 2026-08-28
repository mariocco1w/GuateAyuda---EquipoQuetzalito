/* GESTOR SPA Y CHAT IA - GUATEAYUDA */

document.addEventListener("DOMContentLoaded", () => {
    console.log("GuateAyuda iniciado correctamente.");

    const navItems = document.querySelectorAll(".nav-item");
    const inicioSection = document.getElementById("inicio");
    const dashboardSection = document.getElementById("dashboard");
    const chatSection = document.getElementById("chat");
    const licenciaSection = document.getElementById("licencia");
    const clientesSection = document.getElementById("clientes");
    const faqSection = document.getElementById("faq");

    const negocioId = 1; // Comedor Doña María (Caso principal demo)

    function ocultarTodasLasSecciones() {
        if (inicioSection) inicioSection.style.display = "none";
        if (dashboardSection) dashboardSection.style.display = "none";
        if (chatSection) chatSection.style.display = "none";
        if (licenciaSection) licenciaSection.style.display = "none";
        if (clientesSection) clientesSection.style.display = "none";
        if (faqSection) faqSection.style.display = "none";
    }

    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            navItems.forEach(nav => nav.classList.remove("active"));
            item.classList.add("active");
            ocultarTodasLasSecciones();

            const targetId = item.getAttribute("href");
            if (targetId === "#inicio" && inicioSection) {
                inicioSection.style.display = "block";
            } else if (targetId === "#dashboard" && dashboardSection) {
                dashboardSection.style.display = "block";
                cargarDashboard();
            } else if (targetId === "#chat" && chatSection) {
                chatSection.style.display = "block";
            } else if (targetId === "#licencia" && licenciaSection) {
                licenciaSection.style.display = "block";
            } else if (targetId === "#clientes" && clientesSection) {
                clientesSection.style.display = "block";
            } else if (targetId === "#faq" && faqSection) {
                faqSection.style.display = "block";
            }
        });
    });

    // Cargar Dashboard
    function cargarDashboard() {
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
                if (items.length === 0) {
                    contenedor.innerHTML = "<p style='color: #3A8F5B;'>Todo el inventario está en niveles óptimos.</p>";
                } else {
                    contenedor.innerHTML = items.map(i => `<div style='padding: 6px 0; border-bottom: 1px solid #F0F6F7;'><strong>${i.producto}</strong>: ${i.existencia} en existencia (Mín: ${i.minimo})</div>`).join("");
                }
            })
            .catch(err => console.error("Error inventario bajo:", err));

        fetch(`/api/negocio/${negocioId}/top-productos?n=3`)
            .then(res => res.json())
            .then(data => {
                const contenedor = document.getElementById("lista-top-productos");
                const items = data.top_productos || [];
                if (items.length === 0) {
                    contenedor.innerHTML = "<p>Sin ventas registradas aún.</p>";
                } else {
                    contenedor.innerHTML = items.map(p => `<div style='padding: 6px 0; border-bottom: 1px solid #F0F6F7;'><strong>${p.producto}</strong> — ${p.unidades} un. (Q${p.ingresos.toLocaleString()})</div>`).join("");
                }
            })
            .catch(err => console.error("Error top productos:", err));
    }

    // Chat IA Lógica
    let tokenSesionActual = null;
    let mensajeHumanoActual = null;

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
                tokenSesionActual = body.token_sesion;
                mensajeHumanoActual = body.mensaje_humano;
                
                const op = body.operacion;
                let detalleHtml = `<strong>Tipo:</strong> ${body.tipo.toUpperCase()}<br>`;
                if (body.tipo === "venta") {
                    detalleHtml += `<strong>Producto:</strong> ${op.producto}<br>`;
                    detalleHtml += `<strong>Cantidad:</strong> ${op.cantidad}<br>`;
                    detalleHtml += `<strong>Precio Unitario:</strong> Q${op.precio_unitario}<br>`;
                } else if (body.tipo === "gasto") {
                    detalleHtml += `<strong>Concepto:</strong> ${op.concepto || op.descripcion}<br>`;
                    detalleHtml += `<strong>Monto:</strong> Q${op.monto}<br>`;
                } else if (body.tipo === "inventario") {
                    detalleHtml += `<strong>Producto:</strong> ${op.producto}<br>`;
                    detalleHtml += `<strong>Existencia:</strong> ${op.existencia}<br>`;
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
            if (!tokenSesionActual) return;

            chatStatus.textContent = "Guardando operación...";
            fetch(`/api/negocio/${negocioId}/operacion`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token_sesion: tokenSesionActual, mensaje_humano: mensajeHumanoActual })
            })
            .then(res => res.json())
            .then(data => {
                if (data.guardado) {
                    chatStatus.innerHTML = "<span style='color: #3A8F5B; font-weight: bold;'>¡Operación guardada con éxito! Dashboard actualizado.</span>";
                    resultadoContainer.style.display = "none";
                    inputMensaje.value = "";
                    tokenSesionActual = null;
                } else {
                    chatStatus.textContent = data.mensaje || "Error al guardar.";
                }
            })
            .catch(err => {
                console.error(err);
                chatStatus.textContent = "Error al confirmar operación.";
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
