import requests
from django.core.cache import cache
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from unittest import mock
from core.views import CLUSTER_QUERIES
from core.sitemaps import StaticViewSitemap
from core.redis_client import RedisClient


class HomepageViewTests(TestCase):
    def test_homepage_status_code(self):
        response = self.client.get(reverse('core:core_home'))
        self.assertEqual(response.status_code, 200)

    def test_homepage_template_used(self):
        response = self.client.get(reverse('core:core_home'))
        self.assertTemplateUsed(response, 'core/index.html')

    def test_personal_host_links_to_portfolio(self):
        response = self.client.get('/', HTTP_HOST='raphaelwieland.com')
        self.assertTemplateUsed(response, 'core/index.html')
        self.assertContains(response, 'https://wielandtech.com/')


class SiteDomainTests(TestCase):
    def test_site_points_at_personal_domain(self):
        # Sitemap and password-reset links are built from this domain.
        from django.contrib.sites.models import Site
        self.assertEqual(Site.objects.get_current().domain, 'raphaelwieland.com')


class StaticViewSitemapTests(SimpleTestCase):
    def setUp(self):
        self.sitemap = StaticViewSitemap()

    def test_items(self):
        self.assertEqual(self.sitemap.items(), ['core:core_home'])

    def test_location(self):
        self.assertEqual(self.sitemap.location('core:core_home'), '/')


class RedisClientTests(TestCase):
    @mock.patch('core.redis_client.settings')
    @mock.patch('core.redis_client.Redis')
    def test_get_instance_creates_singleton(self, mock_redis_class, mock_settings):
        mock_settings.REDIS_HOST = 'localhost'
        mock_settings.REDIS_PORT = 6379
        mock_settings.REDIS_DB = 0

        # Reset instance for test isolation
        RedisClient._instance = None

        instance1 = RedisClient.get_instance()
        instance2 = RedisClient.get_instance()

        self.assertIs(instance1, instance2)
        mock_redis_class.assert_called_once_with(
            host='localhost', port=6379, db=0, decode_responses=True
        )


LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def _prom_response(value):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    result = [] if value is None else [{'metric': {}, 'value': [0, str(value)]}]
    response.json.return_value = {'status': 'success', 'data': {'result': result}}
    return response


def _prom_range_response(values):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    result = [] if values is None else [{'metric': {}, 'values': [[i * 86400, str(v)] for i, v in enumerate(values)]}]
    response.json.return_value = {'status': 'success', 'data': {'result': result}}
    return response


@override_settings(CACHES=LOCMEM_CACHE)
class ClusterMetricsViewTests(TestCase):
    SAMPLES = {
        'cpu_percent': 31.234,
        'cpu_cores': 18,
        'mem_used_bytes': 26 * 2**30,
        'mem_total_bytes': 46.3 * 2**30,
        'availability_percent': 99.97749,
        'probed_services': 18,
        'nodes': 4,
        'nodes_ready': 4,
        'uptime_seconds': 205430,
        'pods_running': 145,
        'deployments_total': 82,
        'deployments_healthy': 81,
        'requests_per_second': 1.948,
        'latency_p99_seconds': 0.0996,
        'error_percent': 0.0412,
        'db_size_bytes': 369584143,
        'db_count': 21,
    }

    def setUp(self):
        cache.clear()
        self.url = reverse('core:cluster_metrics')

    DAILY = [100, 99.97957, 100, 99.59150]

    def _fake_get(self, overrides=None):
        samples = {**self.SAMPLES, 'availability_daily': self.DAILY, **(overrides or {})}
        daily = samples.pop('availability_daily')
        by_query = {CLUSTER_QUERIES[k]: v for k, v in samples.items()}

        def fake_get(url, params, timeout):
            if url.endswith('/query_range'):
                if isinstance(daily, Exception):
                    raise daily
                return _prom_range_response(daily)
            value = by_query[params['query']]
            if isinstance(value, Exception):
                raise value
            return _prom_response(value)
        return fake_get

    def test_happy_path_shapes_and_rounds(self):
        with mock.patch('core.views.requests.get', side_effect=self._fake_get()):
            data = self.client.get(self.url).json()

        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['errors'], [])
        self.assertEqual(data['cpu'], {'percentage': 31.2, 'total_cores': 18, 'description': 'CPU Utilization'})
        self.assertEqual(data['memory']['used_gb'], 26.0)
        self.assertEqual(data['memory']['total_gb'], 46.3)
        self.assertEqual(data['memory']['percentage'], 56.2)
        self.assertEqual(data['availability']['percentage'], 99.97)  # floored
        self.assertEqual(data['availability']['services'], 18)
        self.assertEqual(data['deployments']['healthy'], 81)
        self.assertEqual(data['deployments']['total'], 82)
        self.assertEqual(data['pods']['count'], 145)
        self.assertEqual(data['nodes']['count'], 4)
        self.assertEqual(data['traffic']['requests_per_second'], 1.9)
        self.assertEqual(data['database'], {'size_mb': 370, 'databases': 21, 'description': 'Postgres Data'})

    def test_w_portfolio_contract(self):
        # wielandtech.com (wielandtech-labs/w_portfolio) proxies this endpoint
        # and reads these paths in src/components/LiveStats.astro.
        with mock.patch('core.views.requests.get', side_effect=self._fake_get()):
            data = self.client.get(self.url).json()

        paths = [
            'pods.count', 'deployments.healthy', 'deployments.total',
            'availability.percentage', 'availability.services', 'availability.state',
            'availability.slo_met',
            'nodes.count', 'nodes.ready', 'traffic.requests_per_second',
            'database.size_mb', 'database.databases',
            'latency.p99_ms', 'error_rate.percentage',
            'cpu.percentage', 'memory.percentage',
            # legacy, until w_portfolio's new LiveStats is in prod
            'cpu.total_cores', 'memory.used_gb', 'memory.total_gb', 'uptime.formatted',
            'nodes_count', 'reachable_nodes',
        ]
        for path in paths:
            node = data
            for part in path.split('.'):
                self.assertIn(part, node, path)
                node = node[part]
            self.assertIsInstance(node, (int, float, str), path)

        self.assertEqual(data['nodes'], {'count': 4, 'ready': 4, 'description': 'Nodes'})
        self.assertEqual((data['nodes_count'], data['reachable_nodes']), (4, 4))
        self.assertEqual(data['uptime']['formatted'], '2d 9h')
        # The SLO graph: daily availability, oldest first, floored like the card
        self.assertEqual(data['availability']['daily'], [100.0, 99.97, 100.0, 99.59])

    def test_failed_daily_query_keeps_availability_card(self):
        for failure in (requests.exceptions.HTTPError('500'), None):
            cache.clear()
            with mock.patch('core.views.requests.get', side_effect=self._fake_get({'availability_daily': failure})):
                data = self.client.get(self.url).json()
            self.assertEqual(data['availability']['percentage'], 99.97)
            self.assertIsNone(data['availability']['daily'])
            self.assertEqual(data['errors'], ['availability_daily'] if failure else [])

    def test_failed_ready_query_omits_legacy_node_fields(self):
        overrides = {'nodes_ready': requests.exceptions.HTTPError('500')}
        with mock.patch('core.views.requests.get', side_effect=self._fake_get(overrides)):
            data = self.client.get(self.url).json()

        self.assertIsNone(data['nodes']['ready'])
        self.assertNotIn('nodes_count', data)
        self.assertNotIn('reachable_nodes', data)

    def test_failed_query_only_nulls_its_card(self):
        overrides = {'requests_per_second': requests.exceptions.HTTPError('500')}
        with mock.patch('core.views.requests.get', side_effect=self._fake_get(overrides)):
            data = self.client.get(self.url).json()

        self.assertIsNone(data['traffic'])
        self.assertEqual(data['errors'], ['requests_per_second'])
        self.assertIsNotNone(data['cpu'])

    def test_availability_slo_tiers(self):
        # Floored, so the shown number and its tier always agree
        cases = [
            (100.0, 100.0, 99.9, 'healthy'),
            (99.996, 99.99, 99.9, 'healthy'),
            (99.9, 99.9, 99.9, 'healthy'),
            (99.8996, 99.89, 99.0, 'at_risk'),
            (99.0, 99.0, 99.0, 'at_risk'),
            (98.999, 98.99, None, 'breached'),
            (99.29, 99.29, 99.0, 'at_risk'),  # float-error case for naive flooring
        ]
        for raw, shown, slo_met, state in cases:
            cache.clear()
            with mock.patch('core.views.requests.get', side_effect=self._fake_get({'availability_percent': raw})):
                a = self.client.get(self.url).json()['availability']
            self.assertEqual((a['percentage'], a['slo_met'], a['state']), (shown, slo_met, state), raw)

    def test_latency_is_interpolated_p99(self):
        # At or past the top bucket the p99 is unknown; NaN means no traffic
        cases = [(0.0996, 100), (0.4083, 408), (1.0, 1000), (4.9, 4900), (5.0, None),
                 (7.5, None), (float('nan'), None)]
        for raw, p99_ms in cases:
            cache.clear()
            with mock.patch('core.views.requests.get', side_effect=self._fake_get({'latency_p99_seconds': raw})):
                latency = self.client.get(self.url).json()['latency']
            self.assertEqual(latency and latency['p99_ms'], p99_ms, raw)

    def test_public_ingress_excludes_internal_services(self):
        # Long-lived streams (ntfy, Grafana live) would set the public p99
        for key in ('requests_per_second', 'latency_p99_seconds'):
            self.assertIn('service!~"(monitoring|ntfy|homepage)-.*"', CLUSTER_QUERIES[key], key)

    def test_error_rate(self):
        with mock.patch('core.views.requests.get', side_effect=self._fake_get()):
            self.assertEqual(self.client.get(self.url).json()['error_rate']['percentage'], 0.04)
        cache.clear()
        # No ingress traffic at all: 0/0 is NaN, which isn't an error
        with mock.patch('core.views.requests.get', side_effect=self._fake_get({'error_percent': float('nan')})):
            self.assertEqual(self.client.get(self.url).json()['error_rate']['percentage'], 0.0)

    def test_empty_healthy_count_means_zero(self):
        with mock.patch('core.views.requests.get', side_effect=self._fake_get({'deployments_healthy': None})):
            data = self.client.get(self.url).json()

        self.assertEqual(data['deployments']['healthy'], 0)

    def test_failed_healthy_query_hides_deployments_card(self):
        overrides = {'deployments_healthy': requests.exceptions.HTTPError('500')}
        with mock.patch('core.views.requests.get', side_effect=self._fake_get(overrides)):
            data = self.client.get(self.url).json()

        self.assertIsNone(data['deployments'])

    def test_partial_result_does_not_replace_backup(self):
        overrides = {'requests_per_second': requests.exceptions.HTTPError('500')}
        with mock.patch('core.views.requests.get', side_effect=self._fake_get(overrides)):
            self.client.get(self.url)

        self.assertIsNone(cache.get('cluster_metrics_backup'))

    def test_timeout_short_circuits_remaining_queries(self):
        with mock.patch('core.views.requests.get', side_effect=requests.exceptions.ReadTimeout('hung')) as get:
            data = self.client.get(self.url).json()

        self.assertEqual(get.call_count, 1)
        self.assertEqual(data['status'], 'unavailable')

    def test_cache_backend_error_returns_json(self):
        with mock.patch('core.views.cache.get', side_effect=ConnectionError('redis down')):
            data = self.client.get(self.url).json()

        self.assertEqual(data['status'], 'error')

    def test_cache_hit_skips_prometheus(self):
        with mock.patch('core.views.requests.get', side_effect=self._fake_get()) as get:
            self.client.get(self.url)
            calls = get.call_count
            data = self.client.get(self.url).json()

        self.assertEqual(get.call_count, calls)
        self.assertTrue(data['cache_hit'])

    def test_prometheus_down_serves_backup(self):
        with mock.patch('core.views.requests.get', side_effect=self._fake_get()):
            self.client.get(self.url)
        cache.delete('cluster_metrics')

        down = requests.exceptions.ConnectionError('refused')
        with mock.patch('core.views.requests.get', side_effect=down):
            data = self.client.get(self.url).json()

        self.assertEqual(data['status'], 'cached')
        self.assertEqual(data['pods']['count'], 145)

    def test_prometheus_down_without_backup_is_unavailable(self):
        down = requests.exceptions.ConnectionError('refused')
        with mock.patch('core.views.requests.get', side_effect=down):
            data = self.client.get(self.url).json()

        self.assertEqual(data['status'], 'unavailable')
