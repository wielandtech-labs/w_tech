from django.shortcuts import render
from django.http import JsonResponse, Http404
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.contrib import messages
from django.utils.html import format_html
import math
import time
import requests
import logging

logger = logging.getLogger(__name__)


def homepage(request):
    return render(request, 'core/index.html')


def homelab(request):
    """Homelab dashboard page displaying cluster metrics."""
    return render(request, 'core/homelab.html')


def contact(request):
    """Contact page view with form handling and email sending."""
    from .forms import ContactForm

    # Check ReCaptcha configuration
    if not settings.RECAPTCHA_PUBLIC_KEY or not settings.RECAPTCHA_PRIVATE_KEY:
        messages.warning(request, 'Anti-spam verification is not configured. Please contact the administrator if this persists.')
        logger.warning("ReCaptcha keys not configured: RECAPTCHA_PUBLIC_KEY or RECAPTCHA_PRIVATE_KEY missing")
    
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            # Get form data
            cd = form.cleaned_data
            name = cd['name']
            email = cd['email']
            subject = cd['subject']
            message = cd['message']
            
            # Prepare email content
            email_subject = f"Contact Form: {subject}"
            email_message = f"""
New contact form submission from {name} ({email})

Subject: {subject}

Message:
{message}

---
This message was sent from the contact form on {request.get_host()}
            """.strip()
            
            try:
                # Check if email configuration is available
                if not settings.EMAIL_HOST_PASSWORD:
                    messages.error(request, 'Email service is not configured. Please contact the administrator.')
                    logger.error("Email configuration missing: EMAIL_HOST_PASSWORD not set")
                else:
                    # Send email with timeout
                    send_mail(
                        email_subject,
                        email_message,
                        settings.DEFAULT_FROM_EMAIL,
                        [settings.CONTACT_EMAIL],
                        fail_silently=False
                    )
                    messages.success(request, 'Thank you for your message! I will get back to you as soon as possible.')
                    logger.info(f"Contact form email sent successfully from {email}")
                    
                    # Clear the form after successful submission
                    form = ContactForm()
            except Exception as e:
                logger.error(f"Failed to send contact form email: {str(e)}")
                messages.error(request, f'Failed to send message. Please try again later or contact me directly at {settings.CONTACT_EMAIL}')
    else:
        form = ContactForm()
    
    return render(request, 'core/contact.html', {'form': form})


def custom_400(request, exception=None):
    """
    Custom 400 error handler that serves a branded error page.
    This will be used when DEBUG=False and a 400 error occurs.
    """
    return render(request, 'core/400.html', status=400)


def custom_403(request, exception=None):
    """
    Custom 403 error handler that serves a branded error page.
    This will be used when DEBUG=False and a 403 error occurs.
    """
    return render(request, 'core/403.html', status=403)


def custom_404(request, exception=None):
    """
    Custom 404 error handler that serves a branded error page.
    This will be used when DEBUG=False and a 404 error occurs.
    """
    return render(request, 'core/404.html', status=404)


def custom_500(request):
    """
    Custom 500 error handler that serves a branded error page.
    This will be used when DEBUG=False and a 500 error occurs.
    """
    return render(request, 'core/500.html', status=500)


def custom_502(request, exception=None):
    """
    Custom 502 error handler that serves a branded error page.
    This will be used when DEBUG=False and a 502 error occurs.
    """
    return render(request, 'core/502.html', status=502)


def custom_503(request, exception=None):
    """
    Custom 503 error handler that serves a branded error page.
    This will be used when DEBUG=False and a 503 error occurs.
    """
    return render(request, 'core/503.html', status=503)


def maintenance(request):
    """
    Maintenance page handler.
    This can be used to show a maintenance page when needed.
    """
    return render(request, 'core/maintenance.html', status=503)


CLUSTER_METRICS_TTL = 30  # seconds; homelab.js polls on the same interval
CLUSTER_METRICS_BACKUP_TTL = 60 * 60  # served when Prometheus is unreachable
# Availability SLO tiers, highest first; 99.9 matches the w_homelab Grafana SLO dashboards
AVAILABILITY_SLOS = (99.9, 99.0)
# Traefik's default request-duration buckets (seconds). The histogram can't
# resolve within a bucket, so p99 is reported as the bucket bound it falls under.
TRAEFIK_BUCKETS = (0.1, 0.3, 1.2, 5.0)
# The availability card's 30-day window as 30 rolling 24h values, oldest
# first, for w_portfolio's SLO graph. Same expression as availability_percent.
AVAILABILITY_DAILY_QUERY = 'avg(avg_over_time((max by (target) (probe_success))[1d:5m])) * 100'
AVAILABILITY_DAYS = 30

CLUSTER_QUERIES = {
    'cpu_percent': '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))',
    'cpu_cores': 'count(node_cpu_seconds_total{mode="idle"})',
    'mem_used_bytes': 'sum(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)',
    'mem_total_bytes': 'sum(node_memory_MemTotal_bytes)',
    # Share of 5-minute steps each blackbox target was up, averaged over targets
    'availability_percent': 'avg(avg_over_time((max by (target) (probe_success))[30d:5m])) * 100',
    'probed_services': 'count(count by (target) (probe_success))',
    'nodes': 'count(kube_node_info)',
    'nodes_ready': 'sum(kube_node_status_condition{condition="Ready",status="true"})',
    # Most recently rebooted node (node-exporter runs on the bare-metal nodes)
    'uptime_seconds': 'min(time() - node_boot_time_seconds)',
    'pods_running': 'sum(kube_pod_status_phase{phase="Running"})',
    'deployments_total': 'count(kube_deployment_spec_replicas)',
    'deployments_healthy': 'count(kube_deployment_status_replicas_available >= kube_deployment_spec_replicas)',
    'requests_per_second': 'sum(rate(traefik_service_requests_total[5m]))',
    'latency_p99_seconds': 'histogram_quantile(0.99, sum by (le) (rate(traefik_service_request_duration_seconds_bucket[5m])))',
    'error_percent': 'sum(rate(traefik_service_requests_total{code=~"5.."}[5m])) / sum(rate(traefik_service_requests_total[5m])) * 100',
    # CNPG exports the same database from every replica; dedupe by datname
    'db_size_bytes': 'sum(max by (datname) (cnpg_pg_database_size_bytes))',
    'db_count': 'count(max by (datname) (cnpg_pg_database_size_bytes))',
}


def _format_uptime(seconds):
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _availability(raw):
    """Availability floored to 2 decimals, the highest SLO tier it meets, and a state.

    Flooring (with a float-error epsilon) means an imperfect month never reads
    as a higher tier or a perfect 100.00, and the state matches what's shown.
    """
    percentage = math.floor(raw * 100 + 1e-6) / 100
    slo_met = next((slo for slo in AVAILABILITY_SLOS if percentage >= slo), None)
    state = {AVAILABILITY_SLOS[0]: 'healthy', AVAILABILITY_SLOS[1]: 'at_risk'}.get(slo_met, 'breached')
    return percentage, slo_met, state


def _prom(query):
    """Run an instant PromQL query and return the first sample as a float.

    Returns None when the query yields no data. Raises on connection errors so
    the caller can tell "Prometheus is down" apart from "metric missing".
    """
    response = requests.get(
        f"{settings.PROMETHEUS_URL}/api/v1/query",
        params={'query': query},
        timeout=3,
    )
    response.raise_for_status()
    result = response.json().get('data', {}).get('result', [])
    if not result:
        return None
    return float(result[0]['value'][1])


def _availability_daily():
    """AVAILABILITY_DAILY_QUERY at one-day steps ending now, floored like the card.

    Returns None when there's no data; a day with no probes is just missing.
    """
    end = time.time()
    response = requests.get(
        f"{settings.PROMETHEUS_URL}/api/v1/query_range",
        params={
            'query': AVAILABILITY_DAILY_QUERY,
            'start': end - (AVAILABILITY_DAYS - 1) * 86400,
            'end': end,
            'step': 86400,
        },
        timeout=3,
    )
    response.raise_for_status()
    result = response.json().get('data', {}).get('result', [])
    if not result:
        return None
    return [_availability(float(v))[0] for _, v in result[0]['values']]


def get_cluster_metrics(request):
    """
    Cluster metrics for the homelab page, sourced from Prometheus
    (node-exporter, kube-state-metrics, blackbox-exporter, Traefik, CNPG).
    Each card degrades to None independently; results are cached for 30s.
    """
    try:
        return _cluster_metrics_response()
    except Exception as e:
        # e.g. Redis down: keep the JSON contract homelab.js expects
        logger.error(f"Unexpected error fetching cluster metrics: {e}")
        return JsonResponse({'status': 'error', 'error': 'Internal error'})


def _cluster_metrics_response():
    cached_metrics = cache.get('cluster_metrics')
    if cached_metrics:
        cached_metrics['cache_hit'] = True
        return JsonResponse(cached_metrics)

    values = {}
    errors = []
    for key, query in CLUSTER_QUERIES.items():
        try:
            values[key] = _prom(query)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            # Prometheus is unreachable or hung; don't wait on every remaining query
            logger.warning(f"Prometheus unreachable: {e}")
            values = dict.fromkeys(CLUSTER_QUERIES)
            errors = list(CLUSTER_QUERIES)
            break
        except requests.exceptions.RequestException as e:
            logger.warning(f"Prometheus query {key} failed: {e}")
            values[key] = None
            errors.append(key)
        except (KeyError, IndexError, TypeError, ValueError) as e:
            logger.warning(f"Unexpected Prometheus response for {key}: {e}")
            values[key] = None
            errors.append(key)

    if len(errors) == len(CLUSTER_QUERIES):
        backup = cache.get('cluster_metrics_backup')
        if backup:
            backup['status'] = 'cached'
            backup['cache_hit'] = True
            return JsonResponse(backup)
        return JsonResponse({
            'status': 'unavailable',
            'error': 'Unable to connect to monitoring service',
        })

    def present(*keys):
        return all(values[k] is not None for k in keys)

    metrics = {
        'availability': None,
        'deployments': None,
        'pods': None,
        'nodes': None,
        'cpu': None,
        'memory': None,
        'traffic': None,
        'latency': None,
        'error_rate': None,
        'database': None,
        'status': 'ok',
        'cache_hit': False,
        'errors': errors,
    }

    if present('availability_percent', 'probed_services'):
        percentage, slo_met, state = _availability(values['availability_percent'])
        metrics['availability'] = {
            'percentage': percentage,
            'services': int(values['probed_services']),
            'slo_met': slo_met,
            'state': state,
            'daily': None,
            'description': 'Availability (30d)',
        }
        try:
            metrics['availability']['daily'] = _availability_daily()
        except (requests.exceptions.RequestException, KeyError, IndexError, TypeError, ValueError) as e:
            logger.warning(f"Daily availability query failed: {e}")
            errors.append('availability_daily')
    if present('deployments_total') and 'deployments_healthy' not in errors:
        metrics['deployments'] = {
            'total': int(values['deployments_total']),
            # count() of an empty vector returns no data, i.e. zero healthy
            'healthy': int(values['deployments_healthy'] or 0),
            'description': 'Deployments Healthy',
        }
    if present('pods_running'):
        metrics['pods'] = {
            'count': int(values['pods_running']),
            'description': 'Pods Running',
        }
    if present('nodes'):
        metrics['nodes'] = {
            'count': int(values['nodes']),
            'ready': None if 'nodes_ready' in errors else int(values['nodes_ready'] or 0),
            'description': 'Nodes',
        }
    if present('cpu_percent', 'cpu_cores'):
        metrics['cpu'] = {
            'percentage': round(values['cpu_percent'], 1),
            'total_cores': int(values['cpu_cores']),
            'description': 'CPU Utilization',
        }
    if present('mem_used_bytes', 'mem_total_bytes') and values['mem_total_bytes'] > 0:
        metrics['memory'] = {
            'used_gb': round(values['mem_used_bytes'] / 2**30, 1),
            'total_gb': round(values['mem_total_bytes'] / 2**30, 1),
            'percentage': round(values['mem_used_bytes'] / values['mem_total_bytes'] * 100, 1),
            'description': 'Memory Utilization',
        }
    if present('requests_per_second'):
        metrics['traffic'] = {
            'requests_per_second': round(values['requests_per_second'], 1),
            'description': 'Ingress Traffic',
        }
    if present('latency_p99_seconds'):
        # NaN when there was no traffic. In the +Inf bucket Prometheus returns
        # the last finite bound, so a p99 there is unbounded, not <= it.
        p99 = values['latency_p99_seconds']
        bound = next((b for b in TRAEFIK_BUCKETS if p99 <= b), None)
        if p99 >= TRAEFIK_BUCKETS[-1]:
            bound = None
        if bound is not None:
            metrics['latency'] = {
                'p99_ms': round(bound * 1000),
                'description': 'Ingress Latency (p99)',
            }
    if present('error_percent'):
        # 0/0 (no traffic) is NaN: no failed requests
        error_percent = values['error_percent']
        metrics['error_rate'] = {
            'percentage': 0.0 if math.isnan(error_percent) else round(error_percent, 2),
            'description': 'Ingress 5xx Rate',
        }
    if present('db_size_bytes', 'db_count'):
        metrics['database'] = {
            'size_mb': round(values['db_size_bytes'] / 10**6),
            'databases': int(values['db_count']),
            'description': 'Postgres Data',
        }

    # Legacy fields read by w_portfolio's LiveStats (wielandtech.com) until it
    # moves to the cards above; drop them once it no longer does.
    if metrics['nodes'] and metrics['nodes']['ready'] is not None:
        metrics['nodes_count'] = metrics['nodes']['count']
        metrics['reachable_nodes'] = metrics['nodes']['ready']
    metrics['uptime'] = None
    if present('uptime_seconds'):
        metrics['uptime'] = {
            'seconds': int(values['uptime_seconds']),
            'formatted': _format_uptime(values['uptime_seconds']),
            'days': int(values['uptime_seconds'] // 86400),
            'description': 'Uptime',
        }

    cache.set('cluster_metrics', metrics, CLUSTER_METRICS_TTL)
    if not errors:
        # Only a complete snapshot is worth falling back to
        cache.set('cluster_metrics_backup', metrics, CLUSTER_METRICS_BACKUP_TTL)
    return JsonResponse(metrics)


def get_cardinal_direction(degrees):
    """Convert degrees to cardinal direction (N, NE, E, etc.)"""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    index = round(degrees / 22.5) % 16
    return directions[index]


def get_weather_data(request):
    """
    Fetch weather data from Prometheus (Home Assistant metrics).
    Queries the Norton Shores weather station for all available metrics.
    Implements caching to reduce API calls (1 minute TTL).
    """
    cached_weather = cache.get('weather_data')
    if cached_weather:
        cached_weather['cache_hit'] = True
        return JsonResponse(cached_weather)

    try:
        prometheus_url = "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090"
        timeout = 5
        
        weather = {
            'status': 'ok',
            'cache_hit': False,
            'available_metrics': []
        }

        # Query temperature
        temp_query = 'homeassistant_sensor_temperature_celsius{entity="sensor.norton_shores_weather_station_temperature"}'
        temp_response = requests.get(
            f"{prometheus_url}/api/v1/query",
            params={'query': temp_query},
            timeout=timeout
        )

        if temp_response.status_code == 200:
            data = temp_response.json()
            if data.get('status') == 'success' and data.get('data', {}).get('result'):
                temp_celsius = float(data['data']['result'][0]['value'][1])
                weather['temperature_c'] = round(temp_celsius, 1)
                weather['temperature_f'] = round((temp_celsius * 9/5) + 32, 1)
                weather['available_metrics'].append('temperature')

        # Query wind speed
        wind_speed_query = 'homeassistant_sensor_wind_speed_mph{entity="sensor.norton_shores_weather_station_wind_speed"}'
        wind_speed_response = requests.get(
            f"{prometheus_url}/api/v1/query",
            params={'query': wind_speed_query},
            timeout=timeout
        )

        if wind_speed_response.status_code == 200:
            data = wind_speed_response.json()
            if data.get('status') == 'success' and data.get('data', {}).get('result'):
                weather['wind_speed_mph'] = round(float(data['data']['result'][0]['value'][1]), 1)
                weather['available_metrics'].append('wind_speed')

        # Query wind direction (note: u0xb0 is the encoded degree symbol)
        wind_dir_query = 'homeassistant_sensor_wind_direction_u0xb0{entity="sensor.norton_shores_weather_station_wind_direction"}'
        wind_dir_response = requests.get(
            f"{prometheus_url}/api/v1/query",
            params={'query': wind_dir_query},
            timeout=timeout
        )

        if wind_dir_response.status_code == 200:
            data = wind_dir_response.json()
            if data.get('status') == 'success' and data.get('data', {}).get('result'):
                wind_direction = round(float(data['data']['result'][0]['value'][1]))
                weather['wind_direction'] = wind_direction
                weather['wind_direction_cardinal'] = get_cardinal_direction(wind_direction)
                weather['available_metrics'].append('wind_direction')

        # Query humidity (try common patterns)
        humidity_queries = [
            'homeassistant_sensor_humidity_percent{entity="sensor.norton_shores_weather_station_humidity"}',
            'homeassistant_sensor_humidity_percent{entity=~"sensor.norton_shores.*humidity.*"}',
        ]
        for humidity_query in humidity_queries:
            humidity_response = requests.get(
                f"{prometheus_url}/api/v1/query",
                params={'query': humidity_query},
                timeout=timeout
            )
            if humidity_response.status_code == 200:
                data = humidity_response.json()
                if data.get('status') == 'success' and data.get('data', {}).get('result'):
                    weather['humidity'] = round(float(data['data']['result'][0]['value'][1]), 1)
                    weather['available_metrics'].append('humidity')
                    break

        # Query pressure (try common patterns)
        pressure_queries = [
            'homeassistant_sensor_pressure_hpa{entity="sensor.norton_shores_weather_station_pressure"}',
            'homeassistant_sensor_pressure_hpa{entity=~"sensor.norton_shores.*pressure.*"}',
            'homeassistant_sensor_pressure_inhg{entity=~"sensor.norton_shores.*pressure.*"}',
        ]
        for pressure_query in pressure_queries:
            pressure_response = requests.get(
                f"{prometheus_url}/api/v1/query",
                params={'query': pressure_query},
                timeout=timeout
            )
            if pressure_response.status_code == 200:
                data = pressure_response.json()
                if data.get('status') == 'success' and data.get('data', {}).get('result'):
                    pressure_val = float(data['data']['result'][0]['value'][1])
                    # Check if it's in inHg (values typically 28-32) and convert to hPa
                    if pressure_val < 50:
                        weather['pressure_inhg'] = round(pressure_val, 2)
                        weather['pressure_hpa'] = round(pressure_val * 33.8639, 1)
                    else:
                        weather['pressure_hpa'] = round(pressure_val, 1)
                        weather['pressure_inhg'] = round(pressure_val / 33.8639, 2)
                    weather['available_metrics'].append('pressure')
                    break

        # Query UV index
        uv_queries = [
            'homeassistant_sensor_uv_index{entity="sensor.norton_shores_weather_station_uv_index"}',
            'homeassistant_sensor_uv_index{entity=~"sensor.norton_shores.*uv.*"}',
        ]
        for uv_query in uv_queries:
            uv_response = requests.get(
                f"{prometheus_url}/api/v1/query",
                params={'query': uv_query},
                timeout=timeout
            )
            if uv_response.status_code == 200:
                data = uv_response.json()
                if data.get('status') == 'success' and data.get('data', {}).get('result'):
                    weather['uv_index'] = round(float(data['data']['result'][0]['value'][1]), 1)
                    weather['available_metrics'].append('uv_index')
                    break

        # Query precipitation/rain
        rain_queries = [
            'homeassistant_sensor_precipitation_mm{entity=~"sensor.norton_shores.*rain.*"}',
            'homeassistant_sensor_precipitation_in{entity=~"sensor.norton_shores.*rain.*"}',
        ]
        for rain_query in rain_queries:
            rain_response = requests.get(
                f"{prometheus_url}/api/v1/query",
                params={'query': rain_query},
                timeout=timeout
            )
            if rain_response.status_code == 200:
                data = rain_response.json()
                if data.get('status') == 'success' and data.get('data', {}).get('result'):
                    weather['precipitation'] = round(float(data['data']['result'][0]['value'][1]), 2)
                    weather['available_metrics'].append('precipitation')
                    break

        # Build response if we have at least temperature
        if 'temperature_c' in weather:
            cache.set('weather_data', weather, 60)  # 1 minute cache
            cache.set('weather_data_backup', weather, 3600)  # 1 hour backup
            return JsonResponse(weather)
        else:
            logger.warning("No weather data found in Prometheus response")
            return JsonResponse({'status': 'error', 'error': 'No data available'})

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to Prometheus for weather data: {e}")
        # Try to return cached data even if expired
        cached_weather = cache.get('weather_data_backup')
        if cached_weather:
            cached_weather['status'] = 'cached'
            return JsonResponse(cached_weather)
        return JsonResponse({'status': 'error', 'error': 'Unable to connect to monitoring service'})
    except Exception as e:
        logger.error(f"Unexpected error fetching weather data: {e}")
        return JsonResponse({'status': 'error', 'error': 'Internal error'})


def weather(request):
    """Weather station page displaying current conditions and historical data."""
    return render(request, 'core/weather.html')


def _query_prometheus_range(prometheus_url, query, start_time, end_time, step, timeout):
    """Query Prometheus query_range and return list of {time, value} dicts."""
    response = requests.get(
        f"{prometheus_url}/api/v1/query_range",
        params={'query': query, 'start': start_time, 'end': end_time, 'step': step},
        timeout=timeout
    )
    if response.status_code != 200:
        return []
    data = response.json()
    if data.get('status') != 'success' or not data.get('data', {}).get('result'):
        return []
    values = data['data']['result'][0].get('values', [])
    return [{'time': int(v[0]), 'value': round(float(v[1]), 1)} for v in values]


def _merge_dedupe_points(points_list):
    """Merge multiple point lists and deduplicate by timestamp."""
    seen = set()
    merged = []
    for points in points_list:
        for p in points:
            if p['time'] not in seen:
                seen.add(p['time'])
                merged.append(p)
    return sorted(merged, key=lambda x: x['time'])


def get_weather_history(request):
    """
    Fetch historical weather data from Prometheus for charting.
    Accepts 'period' parameter: '24h' (default), '7d', '30d', or '365d'.
    For 30d and 365d, uses chunked queries (Prometheus truncates long ranges).
    """
    period = request.GET.get('period', '24h')
    import time
    end_time = int(time.time())
    
    prometheus_url = "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090"
    timeout = 60 if period == '365d' else (30 if period == '30d' else 10)
    
    history = {
        'period': period,
        'start_time': None,
        'end_time': end_time,
        'temperature': [],
        'wind_speed': [],
        'humidity': [],
        'pressure': [],
        'status': 'ok'
    }
    
    temp_query = 'homeassistant_sensor_temperature_celsius{entity="sensor.norton_shores_weather_station_temperature"}'
    wind_query = 'homeassistant_sensor_wind_speed_mph{entity="sensor.norton_shores_weather_station_wind_speed"}'
    humidity_query = 'homeassistant_sensor_humidity_percent{entity=~"sensor.norton_shores.*humidity.*"}'
    pressure_query = 'homeassistant_sensor_pressure_hpa{entity=~"sensor.norton_shores.*pressure.*"}'
    
    try:
        if period == '24h':
            duration = 24 * 60 * 60
            start_time = end_time - duration
            step = '5m'
            history['start_time'] = start_time
            history['temperature'] = _query_prometheus_range(
                prometheus_url, temp_query, start_time, end_time, step, timeout)
            history['wind_speed'] = _query_prometheus_range(
                prometheus_url, wind_query, start_time, end_time, step, timeout)
            history['humidity'] = _query_prometheus_range(
                prometheus_url, humidity_query, start_time, end_time, step, timeout)
            history['pressure'] = _query_prometheus_range(
                prometheus_url, pressure_query, start_time, end_time, step, timeout)
            
        elif period == '7d':
            duration = 7 * 24 * 60 * 60
            start_time = end_time - duration
            step = '1h'
            history['start_time'] = start_time
            history['temperature'] = _query_prometheus_range(
                prometheus_url, temp_query, start_time, end_time, step, timeout)
            history['wind_speed'] = _query_prometheus_range(
                prometheus_url, wind_query, start_time, end_time, step, timeout)
            history['humidity'] = _query_prometheus_range(
                prometheus_url, humidity_query, start_time, end_time, step, timeout)
            history['pressure'] = _query_prometheus_range(
                prometheus_url, pressure_query, start_time, end_time, step, timeout)
            
        elif period == '30d':
            # Chunk into 5 x 6-day queries (Prometheus truncates single long-range query)
            duration = 30 * 24 * 60 * 60
            start_time = end_time - duration
            history['start_time'] = start_time
            chunk_days = 6
            chunk_sec = chunk_days * 24 * 60 * 60
            step = '1h'
            temp_chunks, wind_chunks, humidity_chunks, pressure_chunks = [], [], [], []
            for i in range(5):
                c_start = start_time + i * chunk_sec
                c_end = min(c_start + chunk_sec, end_time)
                temp_chunks.append(_query_prometheus_range(
                    prometheus_url, temp_query, c_start, c_end, step, timeout))
                wind_chunks.append(_query_prometheus_range(
                    prometheus_url, wind_query, c_start, c_end, step, timeout))
                humidity_chunks.append(_query_prometheus_range(
                    prometheus_url, humidity_query, c_start, c_end, step, timeout))
                pressure_chunks.append(_query_prometheus_range(
                    prometheus_url, pressure_query, c_start, c_end, step, timeout))
            history['temperature'] = _merge_dedupe_points(temp_chunks)
            history['wind_speed'] = _merge_dedupe_points(wind_chunks)
            history['humidity'] = _merge_dedupe_points(humidity_chunks)
            history['pressure'] = _merge_dedupe_points(pressure_chunks)
            
        elif period == '365d':
            # Chunk into 26 x 14-day queries (small enough to avoid Prometheus truncation)
            duration = 365 * 24 * 60 * 60
            start_time = end_time - duration
            history['start_time'] = start_time
            chunk_days = 14
            chunk_sec = chunk_days * 24 * 60 * 60
            step = '6h'  # ~56 points per chunk
            temp_chunks, wind_chunks, humidity_chunks, pressure_chunks = [], [], [], []
            for i in range(26):
                c_start = start_time + i * chunk_sec
                c_end = min(c_start + chunk_sec, end_time)
                temp_chunks.append(_query_prometheus_range(
                    prometheus_url, temp_query, c_start, c_end, step, timeout))
                wind_chunks.append(_query_prometheus_range(
                    prometheus_url, wind_query, c_start, c_end, step, timeout))
                humidity_chunks.append(_query_prometheus_range(
                    prometheus_url, humidity_query, c_start, c_end, step, timeout))
                pressure_chunks.append(_query_prometheus_range(
                    prometheus_url, pressure_query, c_start, c_end, step, timeout))
            history['temperature'] = _merge_dedupe_points(temp_chunks)
            history['wind_speed'] = _merge_dedupe_points(wind_chunks)
            history['humidity'] = _merge_dedupe_points(humidity_chunks)
            history['pressure'] = _merge_dedupe_points(pressure_chunks)
            
        else:
            duration = 24 * 60 * 60
            start_time = end_time - duration
            history['start_time'] = start_time
            step = '5m'
            history['temperature'] = _query_prometheus_range(
                prometheus_url, temp_query, start_time, end_time, step, timeout)
            history['wind_speed'] = _query_prometheus_range(
                prometheus_url, wind_query, start_time, end_time, step, timeout)
            history['humidity'] = _query_prometheus_range(
                prometheus_url, humidity_query, start_time, end_time, step, timeout)
            history['pressure'] = _query_prometheus_range(
                prometheus_url, pressure_query, start_time, end_time, step, timeout)
        
        return JsonResponse(history)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch weather history from Prometheus: {e}")
        return JsonResponse({'status': 'error', 'error': 'Unable to connect to monitoring service'})
    except Exception as e:
        logger.error(f"Unexpected error fetching weather history: {e}")
        return JsonResponse({'status': 'error', 'error': 'Internal error'})
