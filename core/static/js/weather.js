// Weather Station JavaScript
// Handles fetching weather data and rendering charts

let temperatureChart = null;
let windChart = null;
let currentPeriod = '24h';

// Chart.js default configuration for dark/light mode compatibility
function getChartOptions(yAxisLabel) {
    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary').trim() || '#888';
    const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--border-color').trim() || '#333';
    
    return {
        responsive: true,
        maintainAspectRatio: true,
        interaction: {
            intersect: false,
            mode: 'index'
        },
        plugins: {
            legend: {
                display: false
            },
            tooltip: {
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                titleColor: '#fff',
                bodyColor: '#fff',
                padding: 12,
                cornerRadius: 8,
                displayColors: false,
                callbacks: {
                    title: function(context) {
                        const date = new Date(context[0].parsed.x);
                        return date.toLocaleString();
                    }
                }
            }
        },
        scales: {
            x: {
                type: 'time',
                time: {
                    displayFormats: {
                        hour: 'ha',
                        day: 'MMM d'
                    }
                },
                grid: {
                    color: gridColor,
                    drawBorder: false
                },
                ticks: {
                    color: textColor,
                    maxTicksLimit: 8
                }
            },
            y: {
                grid: {
                    color: gridColor,
                    drawBorder: false
                },
                ticks: {
                    color: textColor
                },
                title: {
                    display: true,
                    text: yAxisLabel,
                    color: textColor
                }
            }
        }
    };
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// Muted placeholder when there is no recent reading (or the API is unreachable)
function showNoReading(message) {
    setText('stat-temp', '--');
    setText('stat-temp-detail', ' ');
    setText('stat-wind', '--');
    setText('stat-wind-detail', ' ');
    setText('update-time', '');
    setText('wind-speed-large', '--');
    setText('wind-cardinal-large', '--');
    setText('wind-degrees', '--');
    document.getElementById('current-conditions').innerHTML =
        `<div class="conditions-empty">${message}</div>`;
}

// Fetch and display current weather conditions
function fetchCurrentConditions() {
    fetch('/api/weather/')
        .then(response => response.json())
        .then(data => {
            if (data.temperature_f === undefined) {
                showNoReading(data.status === 'no_data'
                    ? 'No reading in the last hour'
                    : 'Weather data temporarily unavailable');
                return;
            }

            // Stat tiles
            setText('stat-temp', data.temperature_f);
            setText('stat-temp-detail', `${data.temperature_c}°C`);
            if (data.wind_speed_mph !== undefined) {
                setText('stat-wind', data.wind_speed_mph);
                setText('stat-wind-detail', data.wind_direction_cardinal
                    ? `from ${data.wind_direction_cardinal} (${data.wind_direction}°)`
                    : ' ');
            } else {
                setText('stat-wind', '--');
                setText('stat-wind-detail', ' ');
            }

            let html = '<div class="conditions-grid">';

            // Humidity
            if (data.humidity !== undefined) {
                html += `
                    <div class="condition-card">
                        <div class="condition-icon">💧</div>
                        <div class="condition-label">Humidity</div>
                        <div class="condition-value">${data.humidity}<span class="condition-unit">%</span></div>
                    </div>
                `;
            }
            
            // Pressure
            if (data.pressure_inhg !== undefined) {
                html += `
                    <div class="condition-card">
                        <div class="condition-icon">📊</div>
                        <div class="condition-label">Pressure</div>
                        <div class="condition-value">${data.pressure_inhg}<span class="condition-unit"> inHg</span></div>
                        <div class="condition-detail">${data.pressure_hpa} hPa</div>
                    </div>
                `;
            }
            
            // UV Index
            if (data.uv_index !== undefined) {
                let uvLevel = 'Low';
                if (data.uv_index >= 8) uvLevel = 'Very High';
                else if (data.uv_index >= 6) uvLevel = 'High';
                else if (data.uv_index >= 3) uvLevel = 'Moderate';
                
                html += `
                    <div class="condition-card">
                        <div class="condition-icon">☀️</div>
                        <div class="condition-label">UV Index</div>
                        <div class="condition-value">${data.uv_index}</div>
                        <div class="condition-detail">${uvLevel}</div>
                    </div>
                `;
            }
            
            // Precipitation
            if (data.precipitation !== undefined) {
                html += `
                    <div class="condition-card">
                        <div class="condition-icon">🌧️</div>
                        <div class="condition-label">Rain Today</div>
                        <div class="condition-value">${data.precipitation}<span class="condition-unit"> in</span></div>
                    </div>
                `;
            }
            
            html += '</div>';
            document.getElementById('current-conditions').innerHTML = html;
            
            // Update wind display
            updateWindDisplay(data);
            
            // Time of the reading itself, not of the page refresh
            if (data.as_of) {
                const asOf = new Date(data.as_of * 1000);
                setText('update-time', `as of ${asOf.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`);
            }
        })
        .catch(error => {
            console.error('Error fetching weather data:', error);
            showNoReading('Weather data temporarily unavailable');
        });
}

// Update wind compass and display
function updateWindDisplay(data) {
    // Update wind speed
    if (data.wind_speed_mph !== null && data.wind_speed_mph !== undefined) {
        document.getElementById('wind-speed-large').textContent = data.wind_speed_mph;
    }
    
    // Update wind direction
    if (data.wind_direction !== null && data.wind_direction !== undefined) {
        document.getElementById('wind-degrees').textContent = data.wind_direction;
        
        // Rotate compass arrow
        const arrow = document.getElementById('wind-arrow-large');
        if (arrow) {
            arrow.setAttribute('transform', `rotate(${data.wind_direction}, 100, 100)`);
        }
    }
    
    // Update cardinal direction
    if (data.wind_direction_cardinal) {
        document.getElementById('wind-cardinal-large').textContent = data.wind_direction_cardinal;
    }
}

// Fetch historical data and render charts
function fetchHistoricalData(period) {
    currentPeriod = period;
    
    fetch(`/api/weather/history/?period=${period}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'error') {
                console.error('Error fetching historical data:', data.error);
                return;
            }
            
            renderTemperatureChart(data.temperature, period, data.start_time, data.end_time);
            renderWindChart(data.wind_speed, period, data.start_time, data.end_time);
        })
        .catch(error => {
            console.error('Error fetching historical data:', error);
        });
}

// Render temperature chart
function renderTemperatureChart(data, period, startTime, endTime) {
    const ctx = document.getElementById('temperature-chart');
    if (!ctx) return;
    
    // Convert data to Chart.js format
    const chartData = data.map(point => ({
        x: point.time * 1000, // Convert to milliseconds
        y: (point.value * 9/5) + 32 // Convert C to F
    }));
    
    // Get accent color from CSS
    const accentColor = getComputedStyle(document.documentElement).getPropertyValue('--accent-primary').trim() || '#00d4ff';
    
    if (temperatureChart) {
        temperatureChart.destroy();
    }
    
    temperatureChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                data: chartData,
                borderColor: accentColor,
                backgroundColor: accentColor + '20',
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 5,
                borderWidth: 2
            }]
        },
        options: {
            ...getChartOptions('Temperature (°F)'),
            scales: {
                ...getChartOptions('Temperature (°F)').scales,
                x: {
                    ...getChartOptions('Temperature (°F)').scales.x,
                    min: startTime && endTime ? startTime * 1000 : undefined,
                    max: startTime && endTime ? endTime * 1000 : undefined,
                    time: {
                        unit: period === '365d' ? 'month' : (period === '7d' || period === '30d') ? 'day' : 'hour',
                        displayFormats: {
                            hour: 'ha',
                            day: 'MMM d',
                            week: 'MMM d',
                            month: 'MMM yyyy'
                        }
                    }
                }
            }
        }
    });
}

// Render wind speed chart
function renderWindChart(data, period, startTime, endTime) {
    const ctx = document.getElementById('wind-chart');
    if (!ctx) return;
    
    // Convert data to Chart.js format
    const chartData = data.map(point => ({
        x: point.time * 1000,
        y: point.value
    }));
    
    // Use a secondary color for wind
    const highlightColor = getComputedStyle(document.documentElement).getPropertyValue('--highlight').trim() || '#00ff88';
    
    if (windChart) {
        windChart.destroy();
    }
    
    windChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                data: chartData,
                borderColor: highlightColor,
                backgroundColor: highlightColor + '20',
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 5,
                borderWidth: 2
            }]
        },
        options: {
            ...getChartOptions('Wind Speed (mph)'),
            scales: {
                ...getChartOptions('Wind Speed (mph)').scales,
                x: {
                    ...getChartOptions('Wind Speed (mph)').scales.x,
                    min: startTime && endTime ? startTime * 1000 : undefined,
                    max: startTime && endTime ? endTime * 1000 : undefined,
                    time: {
                        unit: period === '365d' ? 'month' : (period === '7d' || period === '30d') ? 'day' : 'hour',
                        displayFormats: {
                            hour: 'ha',
                            day: 'MMM d',
                            week: 'MMM d',
                            month: 'MMM yyyy'
                        }
                    }
                },
                y: {
                    ...getChartOptions('Wind Speed (mph)').scales.y,
                    min: 0
                }
            }
        }
    });
}

// Initialize period toggle buttons
function initPeriodToggle() {
    const buttons = document.querySelectorAll('.period-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', function() {
            // Update active state
            buttons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // Fetch new data
            const period = this.getAttribute('data-period');
            fetchHistoricalData(period);
        });
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Load Chart.js time adapter
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js';
    script.onload = function() {
        // Fetch initial data
        fetchCurrentConditions();
        fetchHistoricalData('24h');
    };
    document.head.appendChild(script);
    
    // Initialize period toggle
    initPeriodToggle();
    
    // Refresh current conditions every minute
    setInterval(fetchCurrentConditions, 60000);
});
