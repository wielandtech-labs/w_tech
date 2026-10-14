// Fetch and display cluster metrics (sourced from Prometheus)
function metricCard(label, value, detail, bar) {
    let barHtml = '';
    if (bar) {
        barHtml = `
            <div class="metric-bar">
                <div class="metric-bar-fill ${bar.cls}" style="width: ${Math.min(bar.percent, 100)}%"></div>
            </div>`;
    }
    return `
        <div class="metric-card">
            <div class="metric-label">${label}</div>
            <div class="metric-value">${value}</div>
            <div class="metric-detail">${detail}</div>${barHtml}
        </div>
    `;
}

function fetchMetrics() {
    fetch('/api/metrics/')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'unavailable' || data.status === 'error') {
                let errorMsg = 'Metrics temporarily unavailable';
                if (data.error) {
                    errorMsg += ': ' + data.error;
                }
                document.getElementById('metrics-content').innerHTML =
                    '<div class="metrics-error">' + errorMsg + '</div>';
                return;
            }

            let html = '<div class="metrics-grid">';

            // Row 1: reliability and fleet
            if (data.availability) {
                // Colored by which SLO tier (99.9% / 99%) the month meets
                const a = data.availability;
                const slo = a.slo_met === null ? 'below 99% SLO' : `meets ${a.slo_met}% SLO`;
                html += metricCard(a.description,
                    `<span class="slo-${a.state}">${a.percentage}%</span>`,
                    `${a.services} services · ${slo}`);
            }

            if (data.deployments) {
                const d = data.deployments;
                const unhealthy = d.total - d.healthy;
                html += metricCard(d.description, `${d.healthy}/${d.total}`,
                    unhealthy === 0 ? 'all at desired replicas' : `${unhealthy} degraded`);
            }

            if (data.pods) {
                html += metricCard(data.pods.description, data.pods.count, 'in cluster');
            }

            if (data.nodes) {
                const n = data.nodes;
                html += metricCard(n.description, n.count,
                    n.ready !== null && n.ready !== undefined ? `${n.ready} ready` : 'bare-metal + GPU');
            }

            // Row 2: capacity and traffic
            if (data.cpu) {
                const c = data.cpu;
                const cls = c.percentage > 80 ? 'critical' : (c.percentage > 60 ? 'warning' : '');
                html += metricCard(c.description, `${c.percentage}%`,
                    `${c.total_cores} cores across bare-metal nodes`, {percent: c.percentage, cls: cls});
            }

            if (data.memory) {
                const m = data.memory;
                const cls = m.percentage > 85 ? 'critical' : (m.percentage > 70 ? 'warning' : '');
                html += metricCard(m.description, `${m.percentage}%`,
                    `${m.used_gb} / ${m.total_gb} GB`, {percent: m.percentage, cls: cls});
            }

            if (data.traffic) {
                html += metricCard(data.traffic.description,
                    `${data.traffic.requests_per_second} req/s`, 'through Traefik (5m avg)');
            }

            if (data.database) {
                const db = data.database;
                const size = db.size_mb >= 1000 ? `${(db.size_mb / 1000).toFixed(1)} GB` : `${db.size_mb} MB`;
                html += metricCard(db.description, size, `${db.databases} databases on CNPG`);
            }

            html += '</div>';

            if (data.status === 'cached') {
                html += '<div class="metrics-status">Showing last known values</div>';
            }

            document.getElementById('metrics-content').innerHTML = html;
        })
        .catch(error => {
            console.error('Error fetching metrics:', error);
            document.getElementById('metrics-content').innerHTML =
                '<div class="metrics-error">Unable to load metrics</div>';
        });
}

// Initial fetch
fetchMetrics();

// Refresh every 30 seconds (matches the server-side cache TTL)
setInterval(fetchMetrics, 30000);
