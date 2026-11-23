// Gráfico de barras de gastos e ingresos mes a mes (Chart.js).
// Los datos los escribe Django en la página con el filtro json_script (<script id="datos-grafico">).
(function () {
    var lienzo = document.getElementById("grafico-meses");
    var fuente = document.getElementById("datos-grafico");
    if (!lienzo || !fuente || typeof Chart === "undefined") { return; }
    var datos = JSON.parse(fuente.textContent);

    // Importes en euros con formato español: 12.345 €
    var euros = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

    new Chart(lienzo, {
        type: "bar",
        data: {
            labels: datos.meses,
            datasets: [
                { label: "Gastos", data: datos.gastos, backgroundColor: "#C2410C", borderRadius: 4 },
                { label: "Ingresos", data: datos.ingresos, backgroundColor: "#2E5E1E", borderRadius: 4 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { position: "bottom" },
                tooltip: {
                    callbacks: {
                        label: function (contexto) { return contexto.dataset.label + ": " + euros.format(contexto.parsed.y); },
                        // Debajo de gastos e ingresos, el beneficio del mes
                        footer: function (elementos) {
                            return "Beneficio: " + euros.format(datos.beneficio[elementos[0].dataIndex]);
                        }
                    }
                }
            },
            scales: {
                y: { beginAtZero: true, ticks: { callback: function (valor) { return euros.format(valor); } } },
                x: { grid: { display: false } }
            }
        }
    });
})();
