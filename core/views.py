from django.shortcuts import render
from django.http import JsonResponse, Http404
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.contrib import messages
from django.utils.html import format_html
import requests
import logging
# from kubernetes import client, config  # No longer needed - using k8s_state metrics

logger = logging.getLogger(__name__)


def homepage(request):
    if getattr(request, 'is_portfolio', False):
        return render(request, 'core/portfolio.html')
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


def get_netdata_metrics(request):
    """
    Fetch cluster metrics from Netdata k8s_state collector.
    Shows cluster CPU utilization, memory usage, pod counts, and network activity.
    Implements caching to reduce API calls.
    """
    cached_metrics = cache.get('netdata_metrics')
    if cached_metrics:
        cached_metrics['cache_hit'] = True
        return JsonResponse(cached_metrics)

    try:
        netdata_url = settings.NETDATA_URL
        timeout = 3
        logger.warning(f"Using Netdata URL: {netdata_url}")

        # Cluster constants
        cluster_cores = 18  # 3 nodes * 6 cores per node
        cluster_ram_gb = 48  # 3 nodes * 16GB per node

        metrics = {
            'cpu': None,
            'memory': None,
            'pods': None,
            'network': None,
            'disk_io': None,
            'uptime': None,
            'temperature': None,
            'deployments': None,
            'status': 'ok',
            'cache_hit': False,
            'errors': [],
            'nodes_count': 3,
            'reachable_nodes': 3,
        }

        # Get list of nodes to query
        netdata_hosts = settings.NETDATA_HOSTS
        logger.warning(f"Querying nodes: {netdata_hosts}")

        # Get CPU utilization aggregated across nodes
        try:
            total_cpu_percentage = 0
            node_count = 0

            for node in netdata_hosts:
                try:
                    cpu_response = requests.get(
                        f"{netdata_url}/api/v1/data",
                        params={'chart': 'system.cpu', 'node': node, 'points': 1, 'after': -10},
                        timeout=timeout
                    )

                    logger.warning(f"CPU API call for node {node}: {netdata_url}/api/v1/data?chart=system.cpu&node={node}&points=1&after=-10")
                    logger.warning(f"CPU response status for {node}: {cpu_response.status_code}")

                    if cpu_response.status_code == 200:
                        cpu_data = cpu_response.json()
                        logger.warning(f"CPU response data for {node}: {cpu_data}")
                        if 'data' in cpu_data and len(cpu_data['data']) > 0:
                            latest = cpu_data['data'][0]
                            logger.warning(f"CPU latest data for {node}: {latest}")
                            if len(latest) >= 2:
                                # CPU data is an array of different CPU usage types, sum them for total usage
                                # Skip timestamp (index 0) and sum all CPU values including iowait
                                cpu_values = [v for v in latest[1:] if isinstance(v, (int, float))]
                                node_cpu_usage = sum(cpu_values)
                                logger.warning(f"CPU values for {node}: {cpu_values}, total: {node_cpu_usage}")
                                total_cpu_percentage += node_cpu_usage
                                node_count += 1
                except Exception as e:
                    logger.warning(f"Failed to fetch CPU from node {node}: {e}")
                    continue

            if node_count > 0:
                # Average CPU across all nodes
                avg_cpu_percentage = total_cpu_percentage / node_count
                logger.warning(f"Aggregated CPU: {total_cpu_percentage} total from {node_count} nodes, average: {avg_cpu_percentage}")
                metrics['cpu'] = {
                    'percentage': round(avg_cpu_percentage, 1),
                    'total_cores': cluster_cores,
                    'description': 'CPU Utilization'
                }
            else:
                metrics['cpu'] = {
                    'percentage': 0.0,
                    'total_cores': cluster_cores,
                    'description': 'CPU Utilization (no nodes available)'
                }
        except Exception as e:
            logger.warning(f"Failed to fetch CPU metrics: {e}")
            metrics['cpu'] = {
                'percentage': 0.0,
                'total_cores': cluster_cores,
                'description': 'CPU Utilization (error)'
            }

        # Get memory utilization aggregated across nodes
        try:
            total_used_memory_mb = 0
            total_total_memory_mb = 0
            memory_node_count = 0

            for node in netdata_hosts:
                try:
                    memory_response = requests.get(
                        f"{netdata_url}/api/v1/data",
                        params={'chart': 'system.ram', 'node': node, 'points': 1, 'after': -10},
                        timeout=timeout
                    )

                    logger.warning(f"Memory API call for node {node}: {netdata_url}/api/v1/data?chart=system.ram&node={node}&points=1&after=-10")
                    logger.warning(f"Memory response status for {node}: {memory_response.status_code}")

                    if memory_response.status_code == 200:
                        memory_data = memory_response.json()
                        logger.warning(f"Memory response data for {node}: {memory_data}")
                        if 'data' in memory_data and len(memory_data['data']) > 0:
                            latest = memory_data['data'][0]
                            logger.warning(f"Memory latest data for {node}: {latest}")
                            # Memory data format: [time, free, used, cached, buffers] (in MB)
                            if len(latest) >= 5:
                                memory_free_mb = latest[1] if isinstance(latest[1], (int, float)) else 0
                                memory_used_mb = latest[2] if isinstance(latest[2], (int, float)) else 0
                                memory_cached_mb = latest[3] if isinstance(latest[3], (int, float)) else 0
                                memory_buffers_mb = latest[4] if isinstance(latest[4], (int, float)) else 0

                                # Total memory = used + free + cached + buffers
                                node_total_mb = memory_used_mb + memory_free_mb + memory_cached_mb + memory_buffers_mb
                                logger.warning(f"Memory for {node} - free: {memory_free_mb}MB, used: {memory_used_mb}MB, cached: {memory_cached_mb}MB, buffers: {memory_buffers_mb}MB, total: {node_total_mb}MB")

                                total_used_memory_mb += memory_used_mb
                                total_total_memory_mb += node_total_mb
                                memory_node_count += 1
                except Exception as e:
                    logger.warning(f"Failed to fetch RAM from node {node}: {e}")
                    continue

            if memory_node_count > 0:
                # Calculate cluster-wide memory metrics
                memory_used_gb = round(total_used_memory_mb / 1024, 1)
                memory_total_gb = round(total_total_memory_mb / 1024, 1)
                memory_percentage = round((total_used_memory_mb / total_total_memory_mb) * 100, 1) if total_total_memory_mb > 0 else 0
                logger.warning(f"Total Cluster Memory: {total_used_memory_mb}MB used, {total_total_memory_mb}MB total across {memory_node_count} nodes")

                metrics['memory'] = {
                    'total_gb': memory_total_gb,
                    'used_gb': memory_used_gb,
                    'percentage': memory_percentage,
                    'description': 'Memory Utilization'
                }
            else:
                metrics['memory'] = {
                    'total_gb': cluster_ram_gb,
                    'used_gb': 0.0,
                    'percentage': 0.0,
                    'description': 'Memory Utilization (no nodes available)'
                }
        except Exception as e:
            logger.warning(f"Failed to fetch memory metrics: {e}")
            metrics['memory'] = {
                'total_gb': cluster_ram_gb,
                'used_gb': 0.0,
                'percentage': 0.0,
                'description': 'Memory Utilization (error)'
            }

        # Get pod count from k8s_state collector using API v2 with context aggregation
        try:
            # Use API v2 with contexts to get running pods across all nodes
            # The k8s_state.node_pods_phase context spans multiple nodes
            pods_response = requests.get(
                f"{netdata_url}/api/v2/data",
                params={
                    'contexts': 'k8s_state.node_pods_phase',
                    'dimensions': 'running',
                    'points': 1
                },
                timeout=timeout
            )

            if pods_response.status_code == 200:
                pods_data = pods_response.json()
                # API v2 returns summary.instances with per-node data
                # Sum the 'avg' (which is current value) from each instance
                running_pods = 0
                if 'summary' in pods_data and 'instances' in pods_data['summary']:
                    for instance in pods_data['summary']['instances']:
                        if 'sts' in instance and 'avg' in instance['sts']:
                            running_pods += int(instance['sts']['avg'])

                metrics['pods'] = {
                    'count': running_pods,
                    'description': 'Pods Running'
                }
            else:
                logger.warning(f"Pods API returned status {pods_response.status_code}")
                metrics['pods'] = {
                    'count': 0,
                    'description': 'Pods Running (unavailable)'
                }
        except Exception as e:
            logger.warning(f"Failed to fetch pod counts: {e}")
            metrics['pods'] = {
                'count': 0,
                'description': 'Pods Running (error)'
            }

        # Get network metrics using API v2 with net.net context (aggregates all interfaces)
        # Values are in kilobits/s, sent values are negative
        try:
            net_response = requests.get(
                f"{netdata_url}/api/v2/data",
                params={
                    'contexts': 'net.net',
                    'nodes': ','.join(netdata_hosts),
                    'points': 1,
                    'after': -10  # Get data from last 10 seconds for real-time values
                },
                timeout=timeout
            )

            if net_response.status_code == 200:
                net_data = net_response.json()
                # API v2 returns result.data with format [timestamp, [received, arp, pa], [sent, arp, pa]]
                if 'result' in net_data and 'data' in net_data['result'] and len(net_data['result']['data']) > 0:
                    latest = net_data['result']['data'][0]
                    # Format: [timestamp, [received_value, ...], [sent_value, ...]]
                    received_kbps = 0
                    sent_kbps = 0
                    if len(latest) >= 3:
                        # received is positive, sent is negative in netdata
                        if isinstance(latest[1], list) and len(latest[1]) > 0:
                            received_kbps = abs(latest[1][0]) if isinstance(latest[1][0], (int, float)) else 0
                        if isinstance(latest[2], list) and len(latest[2]) > 0:
                            sent_kbps = abs(latest[2][0]) if isinstance(latest[2][0], (int, float)) else 0

                    # Convert kilobits/s to Mbps (1 Mbps = 1000 kbps)
                    received_mbps = round(received_kbps / 1000, 2)
                    sent_mbps = round(sent_kbps / 1000, 2)

                    # Count how many nodes contributed
                    node_count = len(net_data.get('summary', {}).get('nodes', [])) or len(netdata_hosts)

                    metrics['network'] = {
                        'bandwidth_mbps': round(received_mbps + sent_mbps, 2),
                        'received_mbps': received_mbps,
                        'sent_mbps': sent_mbps,
                        'description': 'Network Utilization'
                    }
                else:
                    metrics['network'] = None
            else:
                logger.warning(f"Network API returned status {net_response.status_code}")
                metrics['network'] = None
        except Exception as e:
            logger.warning(f"Failed to fetch network metrics: {e}")
            metrics['network'] = None

        # Get disk I/O metrics aggregated across nodes
        try:
            total_read_kbps = 0
            total_write_kbps = 0
            disk_node_count = 0

            for node in netdata_hosts:
                try:
                    disk_response = requests.get(
                        f"{netdata_url}/api/v1/data",
                        params={'chart': 'system.io', 'node': node, 'points': 1, 'after': -10},
                        timeout=timeout
                    )

                    if disk_response.status_code == 200:
                        disk_data = disk_response.json()
                        if 'data' in disk_data and len(disk_data['data']) > 0:
                            latest = disk_data['data'][0]
                            # Disk I/O format: [time, in (read), out (write)] in KiB/s
                            if len(latest) >= 3:
                                read_kbps = abs(latest[1]) if isinstance(latest[1], (int, float)) else 0
                                write_kbps = abs(latest[2]) if isinstance(latest[2], (int, float)) else 0
                                total_read_kbps += read_kbps
                                total_write_kbps += write_kbps
                                disk_node_count += 1
                except Exception as e:
                    logger.warning(f"Failed to fetch disk I/O from node {node}: {e}")
                    continue

            if disk_node_count > 0:
                # Convert KiB/s to MB/s
                read_mbps = round(total_read_kbps / 1024, 2)
                write_mbps = round(total_write_kbps / 1024, 2)
                metrics['disk_io'] = {
                    'read_mbps': read_mbps,
                    'write_mbps': write_mbps,
                    'total_mbps': round(read_mbps + write_mbps, 2),
                    'description': 'Disk I/O'
                }
        except Exception as e:
            logger.warning(f"Failed to fetch disk I/O metrics: {e}")
            metrics['disk_io'] = None

        # Get uptime from the first reachable node (representative of cluster)
        try:
            max_uptime_seconds = 0
            min_uptime_seconds = float('inf')

            for node in netdata_hosts:
                try:
                    uptime_response = requests.get(
                        f"{netdata_url}/api/v1/data",
                        params={'chart': 'system.uptime', 'node': node, 'points': 1, 'after': -10},
                        timeout=timeout
                    )

                    if uptime_response.status_code == 200:
                        uptime_data = uptime_response.json()
                        if 'data' in uptime_data and len(uptime_data['data']) > 0:
                            latest = uptime_data['data'][0]
                            if len(latest) >= 2:
                                node_uptime = latest[1] if isinstance(latest[1], (int, float)) else 0
                                max_uptime_seconds = max(max_uptime_seconds, node_uptime)
                                min_uptime_seconds = min(min_uptime_seconds, node_uptime)
                except Exception as e:
                    logger.warning(f"Failed to fetch uptime from node {node}: {e}")
                    continue

            if max_uptime_seconds > 0:
                # Use minimum uptime (most recent reboot) for cluster uptime
                uptime_seconds = min_uptime_seconds if min_uptime_seconds != float('inf') else max_uptime_seconds
                # Convert to days, hours, minutes
                days = int(uptime_seconds // 86400)
                hours = int((uptime_seconds % 86400) // 3600)
                minutes = int((uptime_seconds % 3600) // 60)

                if days > 0:
                    uptime_str = f"{days}d {hours}h"
                elif hours > 0:
                    uptime_str = f"{hours}h {minutes}m"
                else:
                    uptime_str = f"{minutes}m"

                metrics['uptime'] = {
                    'seconds': int(uptime_seconds),
                    'formatted': uptime_str,
                    'days': days,
                    'description': 'Uptime'
                }
        except Exception as e:
            logger.warning(f"Failed to fetch uptime metrics: {e}")
            metrics['uptime'] = None

        # Get CPU temperature using the correct context from Netdata
        try:
            temps = []
            
            # Use API v2 with the correct context for temperature sensors
            temp_response = requests.get(
                f"{netdata_url}/api/v2/data",
                params={
                    'contexts': 'system.hw.sensor.temperature.input',
                    'nodes': ','.join(netdata_hosts),
                    'points': 1
                },
                timeout=timeout
            )

            if temp_response.status_code == 200:
                temp_data = temp_response.json()
                
                # Extract temperatures from dimensions - look for Package or Core temps
                if 'summary' in temp_data and 'dimensions' in temp_data['summary']:
                    for dim in temp_data['summary']['dimensions']:
                        dim_id = dim.get('id', '').lower()
                        # Prioritize Package temps (overall CPU temp), also accept Core temps
                        if 'package' in dim_id or 'coretemp' in dim_id:
                            if 'sts' in dim and 'avg' in dim['sts']:
                                temp_val = dim['sts']['avg']
                                if isinstance(temp_val, (int, float)) and 20 < temp_val < 120:
                                    temps.append(temp_val)
                
                # If no package temps found, try instances
                if not temps and 'summary' in temp_data and 'instances' in temp_data['summary']:
                    for instance in temp_data['summary']['instances']:
                        inst_id = instance.get('id', '').lower()
                        if 'package' in inst_id or 'coretemp' in inst_id:
                            if 'sts' in instance and 'avg' in instance['sts']:
                                temp_val = instance['sts']['avg']
                                if isinstance(temp_val, (int, float)) and 20 < temp_val < 120:
                                    temps.append(temp_val)
                
                logger.warning(f"Temperature data found: {len(temps)} readings")
            else:
                logger.warning(f"Temperature API v2 returned status {temp_response.status_code}")

            if temps:
                avg_temp = round(sum(temps) / len(temps), 1)
                max_temp = round(max(temps), 1)
                metrics['temperature'] = {
                    'avg_celsius': avg_temp,
                    'max_celsius': max_temp,
                    'node_count': len(temps),
                    'description': 'CPU Temperature'
                }
                logger.warning(f"Temperature metrics: avg={avg_temp}, max={max_temp}, readings={len(temps)}")
            else:
                logger.warning("No CPU temperature data found from context")
        except Exception as e:
            logger.warning(f"Failed to fetch temperature metrics: {e}")
            metrics['temperature'] = None

        # Get deployment status from k8s_state collector
        try:
            # Try multiple context names for deployments
            deployment_contexts = [
                'k8s_state.deployment_replicas',
                'k8s_state.deployment_replicas_ready',
                'k8s_state.deployment_condition'
            ]
            
            deploy_data = None
            for context in deployment_contexts:
                deployments_response = requests.get(
                    f"{netdata_url}/api/v2/data",
                    params={
                        'contexts': context,
                        'points': 1
                    },
                    timeout=timeout
                )
                
                if deployments_response.status_code == 200:
                    deploy_data = deployments_response.json()
                    logger.warning(f"Deployments API response for {context}: {deploy_data}")
                    
                    # Check if we got actual data
                    if 'summary' in deploy_data:
                        if 'instances' in deploy_data['summary'] and len(deploy_data['summary']['instances']) > 0:
                            logger.warning(f"Found deployment data using context: {context}")
                            break
                        elif 'dimensions' in deploy_data['summary'] and len(deploy_data['summary']['dimensions']) > 0:
                            logger.warning(f"Found deployment dimensions using context: {context}")
                            break
                    deploy_data = None  # Reset if no useful data

            if deploy_data:
                total_deployments = 0
                healthy_deployments = 0

                # Try to count from instances
                if 'summary' in deploy_data and 'instances' in deploy_data['summary']:
                    for instance in deploy_data['summary']['instances']:
                        total_deployments += 1
                        if 'sts' in instance and 'avg' in instance['sts']:
                            if instance['sts']['avg'] > 0:
                                healthy_deployments += 1
                
                # If no instances, try dimensions (each dimension might be a deployment)
                if total_deployments == 0 and 'summary' in deploy_data and 'dimensions' in deploy_data['summary']:
                    for dim in deploy_data['summary']['dimensions']:
                        total_deployments += 1
                        if 'sts' in dim and 'avg' in dim['sts']:
                            if dim['sts']['avg'] > 0:
                                healthy_deployments += 1

                if total_deployments > 0:
                    metrics['deployments'] = {
                        'total': total_deployments,
                        'healthy': healthy_deployments,
                        'description': 'Deployments'
                    }
                    logger.warning(f"Deployments metrics: {healthy_deployments}/{total_deployments} healthy")
                else:
                    logger.warning("No deployment instances found in response")
            else:
                logger.warning("No deployment data found from any context")
        except Exception as e:
            logger.warning(f"Failed to fetch deployment metrics: {e}")
            metrics['deployments'] = None

        cache.set('netdata_metrics', metrics, 1)

        return JsonResponse(metrics)

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to Netdata: {e}")
        # Try to return cached data even if expired
        cached_metrics = cache.get('netdata_metrics_backup')
        if cached_metrics:
            cached_metrics['status'] = 'cached'
            return JsonResponse(cached_metrics)

        return JsonResponse({
            'cpu': None,
            'memory': None,
            'pods': None,
            'network': None,
            'disk_io': None,
            'uptime': None,
            'temperature': None,
            'deployments': None,
            'status': 'unavailable',
            'error': 'Unable to connect to monitoring service'
        })
    except Exception as e:
        logger.error(f"Unexpected error fetching metrics: {e}")
        return JsonResponse({
            'cpu': None,
            'memory': None,
            'pods': None,
            'network': None,
            'disk_io': None,
            'uptime': None,
            'temperature': None,
            'deployments': None,
            'status': 'error',
            'error': 'Internal error'
        })


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
