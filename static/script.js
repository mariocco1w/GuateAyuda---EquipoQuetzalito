/* PAG INICIO GUATE AYUDA - SISTEMA DE NAVEGACIÓN VISTA SPA */

document.addEventListener("DOMContentLoaded", () => {
    console.log("GuateAyuda iniciado correctamente.");

    // Seleccionamos todos los botones del menú de la izquierda
    const navItems = document.querySelectorAll(".nav-item");
    
    // Seleccionamos los contenedores principales de contenido
    const inicioSection = document.getElementById("inicio");
    const licenciaSection = document.getElementById("licencia");
    const clientesSection = document.getElementById("clientes");
    const faqSection = document.getElementById("faq");

    // Función para ocultar todas las secciones
    function ocultarTodasLasSecciones() {
        if (inicioSection) inicioSection.style.display = "none";
        if (licenciaSection) licenciaSection.style.display = "none";
        if (clientesSection) clientesSection.style.display = "none";
        if (faqSection) faqSection.style.display = "none";
    }

    // Escuchamos el clic en cada opción del menú
    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            // Evitamos el comportamiento por defecto del enlace hash
            e.preventDefault();

            // 1. Quitamos la clase 'active' de todos los botones y se la ponemos al que se clickeó
            navItems.forEach(nav => nav.classList.remove("active"));
            item.classList.add("active");

            // 2. Ocultamos todo primero
            ocultarTodasLasSecciones();

            // 3. Obtenemos el ID a dónde apunta el botón (ej: #licencia, #inicio)
            const targetId = item.getAttribute("href");

            // 4. Mostramos la sección correspondiente
            if (targetId === "#inicio" && inicioSection) {
                inicioSection.style.display = "block";
            } else if (targetId === "#licencia" && licenciaSection) {
                licenciaSection.style.display = "block";
            } else if (targetId === "#clientes" && clientesSection) {
                clientesSection.style.display = "block";
            } else if (targetId === "#faq" && faqSection) {
                faqSection.style.display = "block";
            }
        });
    });
});