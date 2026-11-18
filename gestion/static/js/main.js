// Mostrar u ocultar la contraseña con el botón del ojo
document.querySelectorAll("[data-mostrar-contrasena]").forEach(function (boton) {
    boton.addEventListener("click", function () {
        var campo = document.getElementById(boton.dataset.mostrarContrasena);
        var mostrar = campo.type === "password";
        campo.type = mostrar ? "text" : "password";
        boton.classList.toggle("entrada__ojo--visible", mostrar);
        boton.setAttribute("aria-pressed", mostrar ? "true" : "false");
    });
});

function eliminar() {
    return confirm("¿Seguro que quieres eliminar este proyecto? Se borrarán también todos sus apuntes.");
}
// Avisos («Apuntado…», «Proyecto creado»...): se cierran solos a los 4 segundos.
// Si el ratón está encima, esperan; la X los cierra al momento.
document.querySelectorAll(".avisos .aviso").forEach(function (aviso) {
    var cerrar = document.createElement("button");
    cerrar.type = "button";
    cerrar.className = "aviso__cerrar";
    cerrar.setAttribute("aria-label", "Cerrar aviso");
    cerrar.textContent = "×";
    aviso.appendChild(cerrar);

    var temporizador;
    function ocultar() {
        aviso.classList.add("aviso--saliendo");
        setTimeout(function () { aviso.remove(); }, 300);
    }
    function programar() {
        temporizador = setTimeout(ocultar, 4000);
    }
    cerrar.addEventListener("click", ocultar);
    aviso.addEventListener("mouseenter", function () { clearTimeout(temporizador); });
    aviso.addEventListener("mouseleave", programar);
    programar();
});

// ---------------------------------------------------------------------------
// Selector deslizable de horas y minutos.
// Apartado «Horas de trabajo»: dos ruedas, horas de 0 a 24 y minutos 00, 15, 30 y 45.
// Lo elegido se escribe en el campo «cantidad» en horas con decimales (2 h 30 min = 2.50),
// que es lo que guarda Django.
// ---------------------------------------------------------------------------
var ALTO_OPCION = 40; // alto en píxeles de cada número de la rueda (igual que en el CSS)

function crearRueda(rueda, valores, alCambiar) {
    var elegido = 0;
    var espera = null;

    valores.forEach(function (valor, indice) {
        var opcion = document.createElement("div");
        opcion.className = "reloj__opcion";
        opcion.setAttribute("role", "option");
        opcion.textContent = valor < 10 && valores.length < 10 ? "0" + valor : valor;
        // Al pulsar un número, la rueda se desliza hasta él
        opcion.addEventListener("click", function () { elegir(indice, true); });
        rueda.appendChild(opcion);
    });

    function marcar(indice) {
        elegido = Math.max(0, Math.min(valores.length - 1, indice));
        rueda.querySelectorAll(".reloj__opcion").forEach(function (opcion, i) {
            opcion.classList.toggle("reloj__opcion--elegida", i === elegido);
            opcion.setAttribute("aria-selected", i === elegido ? "true" : "false");
        });
    }

    function elegir(indice, suave) {
        marcar(indice);
        rueda.scrollTo({ top: elegido * ALTO_OPCION, behavior: suave ? "smooth" : "auto" });
        alCambiar();
    }

    // Al deslizar con el dedo o la rueda del ratón: cuando se para, se queda con el número del centro
    rueda.addEventListener("scroll", function () {
        clearTimeout(espera);
        espera = setTimeout(function () {
            var indice = Math.round(rueda.scrollTop / ALTO_OPCION);
            if (indice !== elegido) {
                marcar(indice);
                alCambiar();
            }
        }, 90);
    });

    // Con el teclado: flechas arriba y abajo
    rueda.addEventListener("keydown", function (evento) {
        if (evento.key === "ArrowDown") { evento.preventDefault(); elegir(elegido + 1, true); }
        if (evento.key === "ArrowUp") { evento.preventDefault(); elegir(elegido - 1, true); }
    });

    return {
        valor: function () { return valores[elegido]; },
        elegir: elegir
    };
}

// Cada selector de horas de la página: escribe en el campo oculto «cantidad» del mismo formulario
document.querySelectorAll("[data-reloj]").forEach(function (reloj) {
    var cantidad = reloj.closest("form").querySelector("input[name=cantidad]");
    var listaHoras = [];
    for (var h = 0; h <= 24; h++) { listaHoras.push(h); }
    var listaMinutos = [0, 15, 30, 45];

    var horas = crearRueda(reloj.querySelector("[data-reloj-horas]"), listaHoras, escribir);
    var minutos = crearRueda(reloj.querySelector("[data-reloj-minutos]"), listaMinutos, escribir);

    function escribir() {
        var h = horas.valor();
        var m = minutos.valor();
        // Como mucho 24 h justas
        if (h === 24 && m !== 0) { minutos.elegir(0, true); m = 0; }
        cantidad.value = (h + m / 60).toFixed(2);
    }

    // Botones de tiempos habituales (½ h, 1 h, 4 h, 8 h...): mueven las ruedas
    reloj.closest(".campo").querySelectorAll("[data-tiempo]").forEach(function (boton) {
        boton.addEventListener("click", function () {
            var tiempo = parseFloat(boton.dataset.tiempo);
            horas.elegir(Math.floor(tiempo), true);
            minutos.elegir(Math.round((tiempo - Math.floor(tiempo)) * 4), true);
            escribir();
        });
    });

    // Coloca las ruedas en lo que ya hubiera (1 h al empezar, o el valor al editar)
    var valor = parseFloat(String(cantidad.value).replace(",", ".")) || 1;
    var horaInicial = Math.min(24, Math.floor(valor));
    horas.elegir(horaInicial, false);
    minutos.elegir(Math.round((valor - horaInicial) * 4) % 4, false);
    escribir();
});

// Al elegir un material de la lista, se escribe su unidad junto a la cantidad (m, ud, kg...)
document.querySelectorAll("[data-opciones-material]").forEach(function (formulario) {
    var unidad = formulario.querySelector("[data-unidad-cantidad]");
    function poner() {
        var elegido = formulario.querySelector("input[name=material]:checked");
        unidad.textContent = elegido ? elegido.dataset.unidad : "";
    }
    formulario.addEventListener("change", poner);
    poner();
});

// En el móvil los botones de familia y tipo van en una fila que se desliza:
// se coloca la fila para que se vea el botón elegido.
document.querySelectorAll(".familias, .segmentos--desliza").forEach(function (fila) {
    var activo = fila.querySelector(".familia--activa, .segmento--activo");
    if (activo && fila.scrollWidth > fila.clientWidth) {
        fila.scrollLeft = activo.offsetLeft - fila.offsetLeft - 16;
    }
});

// Pestañas de abajo en el detalle del proyecto: Apuntes, Notas y Albaranes.
// Sin JavaScript se ven las tres seguidas; con él, solo la elegida. La elegida se guarda
// en la dirección (#notas) para que al recargar o volver de guardar siga abierta.
document.querySelectorAll("[data-pestanas]").forEach(function (bloque) {
    var botones = bloque.querySelectorAll("[data-pestana]");
    var nombres = Array.prototype.map.call(botones, function (b) { return b.dataset.pestana; });
    bloque.classList.add("pestanas-proyecto--activas");

    function abrir(nombre, moverPantalla) {
        botones.forEach(function (boton) {
            var elegida = boton.dataset.pestana === nombre;
            boton.classList.toggle("pestana-proyecto--activa", elegida);
            boton.setAttribute("aria-selected", elegida ? "true" : "false");
            document.getElementById(boton.dataset.pestana).hidden = !elegida;
        });
        if (moverPantalla) {
            bloque.scrollIntoView({ block: "start" });
        }
    }

    botones.forEach(function (boton) {
        boton.addEventListener("click", function (evento) {
            evento.preventDefault();
            abrir(boton.dataset.pestana, false);
            history.replaceState(null, "", "#" + boton.dataset.pestana);
        });
    });

    // Pestaña inicial: la de la dirección (#albaranes), la que manda Django si hay errores, o Apuntes
    var desdeDireccion = location.hash.slice(1);
    if (nombres.indexOf(desdeDireccion) !== -1) {
        abrir(desdeDireccion, true);
    } else {
        abrir(nombres.indexOf(bloque.dataset.pestanaInicial) !== -1 ? bloque.dataset.pestanaInicial : nombres[0],
              bloque.dataset.pestanaInicial && bloque.dataset.pestanaInicial !== "apuntes");
    }
});

// Subir albarán: muestra el nombre del PDF elegido y deja soltarlo arrastrándolo encima
document.querySelectorAll("[data-zona-pdf]").forEach(function (zona) {
    var entrada = zona.querySelector("input[type=file]");
    var texto = zona.querySelector("[data-zona-pdf-nombre]");
    var textoInicial = texto.textContent;

    function mostrar() {
        var archivo = entrada.files[0];
        texto.textContent = archivo ? archivo.name : textoInicial;
        zona.classList.toggle("zona-pdf--elegido", Boolean(archivo));
    }
    entrada.addEventListener("change", mostrar);

    ["dragenter", "dragover"].forEach(function (tipo) {
        zona.addEventListener(tipo, function (evento) {
            evento.preventDefault();
            zona.classList.add("zona-pdf--encima");
        });
    });
    ["dragleave", "drop"].forEach(function (tipo) {
        zona.addEventListener(tipo, function () { zona.classList.remove("zona-pdf--encima"); });
    });
    zona.addEventListener("drop", function (evento) {
        evento.preventDefault();
        if (evento.dataTransfer.files.length) {
            entrada.files = evento.dataTransfer.files;
            mostrar();
        }
    });
});

// Horas: varias líneas en el mismo apunte (Oficial · Electricidad 4 h + Peón · Fontanería 6 h).
// «Añadir a la lista» guarda lo elegido como una línea con campos ocultos linea_material,
// linea_campo y linea_cantidad; la vista las lee con request.POST.getlist(). Si la lista está
// vacía, se apunta solo lo elegido, como siempre.
document.querySelectorAll("[data-lineas-horas]").forEach(function (zona) {
    var formulario = zona.closest("form");
    var lista = zona.querySelector("[data-lineas-lista]");
    var ayuda = zona.querySelector("[data-lineas-ayuda]");
    var enviar = formulario.querySelector("[data-lineas-enviar]");
    var textoAyuda = ayuda.textContent;
    zona.hidden = false;

    function elegido(nombre) { return formulario.querySelector("input[name=" + nombre + "]:checked"); }
    function nombreDe(opcion) { return opcion ? opcion.closest("label").textContent.trim() : ""; }
    function horasTexto(valor) {
        var minutos = Math.round(valor * 60);
        var h = Math.floor(minutos / 60), m = minutos % 60;
        if (h && m) { return h + " h " + m + " min"; }
        return m ? m + " min" : h + " h";
    }
    function oculto(nombre, valor) {
        var campo = document.createElement("input");
        campo.type = "hidden"; campo.name = nombre; campo.value = valor;
        return campo;
    }
    function actualizar() {
        var n = lista.children.length;
        enviar.textContent = n ? "Apuntar " + n + (n === 1 ? " línea" : " líneas") : "Apuntar horas";
        zona.classList.toggle("lineas-horas--con-lineas", n > 0);
    }

    zona.querySelector("[data-lineas-anadir]").addEventListener("click", function () {
        // Oficiales y peones: el puesto va en un campo oculto (el de su rol)
        var puestoFijo = formulario.querySelector("[data-puesto-fijo]");
        var puesto = puestoFijo ? formulario.querySelector("input[type=hidden][name=material]") : elegido("material");
        var campo = elegido("campo");
        var hayCampos = formulario.querySelector("input[name=campo]") !== null;
        var cantidad = parseFloat(formulario.querySelector("input[name=cantidad]").value) || 0;
        if (!puesto || (hayCampos && !campo) || cantidad <= 0) {
            ayuda.textContent = "Elige puesto" + (hayCampos ? ", campo" : "") + " y un tiempo mayor que 0 antes de añadir.";
            ayuda.classList.add("lineas-horas__ayuda--error");
            return;
        }
        ayuda.textContent = textoAyuda;
        ayuda.classList.remove("lineas-horas__ayuda--error");

        var linea = document.createElement("li");
        linea.className = "linea-horas";
        var texto = document.createElement("span");
        texto.className = "linea-horas__texto";
        var titulo = document.createElement("strong");
        // Con el puesto fijo solo se enseña el campo (el puesto no lo ve el empleado)
        titulo.textContent = puestoFijo ? (campo ? nombreDe(campo) : "Horas") : nombreDe(puesto) + (campo ? " · " + nombreDe(campo) : "");
        texto.appendChild(titulo);
        texto.appendChild(document.createTextNode(horasTexto(cantidad)));
        var quitar = document.createElement("button");
        quitar.type = "button";
        quitar.className = "linea-horas__quitar";
        quitar.setAttribute("aria-label", "Quitar " + titulo.textContent + " de la lista");
        quitar.textContent = "×";
        quitar.addEventListener("click", function () { linea.remove(); actualizar(); });

        linea.appendChild(texto);
        linea.appendChild(quitar);
        linea.appendChild(oculto("linea_material", puesto.value));
        linea.appendChild(oculto("linea_campo", campo ? campo.value : ""));
        linea.appendChild(oculto("linea_cantidad", cantidad.toFixed(2)));
        lista.appendChild(linea);
        actualizar();
    });
});

// Apartado Citas: escribir en el filtro deja en el desplegable solo los trabajos que coinciden
document.querySelectorAll("[data-filtrar-select]").forEach(function (entrada) {
    var lista = document.getElementById(entrada.dataset.filtrarSelect);
    if (!lista) { return; }
    function sinTildes(texto) { return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
    entrada.addEventListener("input", function () {
        var palabras = sinTildes(entrada.value).split(/\s+/).filter(Boolean);
        var primera = null;
        lista.querySelectorAll("option").forEach(function (opcion) {
            if (!opcion.value) { return; }
            var vale = palabras.every(function (p) { return sinTildes(opcion.textContent).indexOf(p) !== -1; });
            opcion.hidden = !vale;
            if (vale && !primera) { primera = opcion; }
        });
        lista.querySelectorAll("optgroup").forEach(function (grupo) {
            grupo.hidden = !grupo.querySelector("option:not([hidden])");
        });
        // Si solo queda uno (o el elegido ya no sale), se elige el primero que coincide
        var elegida = lista.options[lista.selectedIndex];
        if (primera && (!elegida || !elegida.value || elegida.hidden)) { lista.value = primera.value; }
    });
});
