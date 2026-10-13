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
        'db_size_bytes': 369584143,
        'db_count': 21,
    }

    def setUp(self):
        cache.clear()
        self.url = reverse('core:cluster_metrics')

    def _fake_get(self, overrides=None):
        samples = {**self.SAMPLES, **(overrides or {})}
        by_query = {CLUSTER_QUERIES[k]: v for k, v in samples.items()}

        def fake_get(url, params, timeout):
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
        self.assertEqual(data['availability']['percentage'], 99.98)
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
            'availability.percentage', 'availability.services',
            'nodes.count', 'nodes.ready', 'traffic.requests_per_second',
            'database.size_mb', 'database.databases',
            # legacy, until w_portfolio's new LiveStats is in prod
            'cpu.percentage', 'cpu.total_cores', 'memory.percentage',
            'memory.used_gb', 'memory.total_gb', 'uptime.formatted',
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

    def test_imperfect_availability_never_rounds_to_100(self):
        for raw, shown in [(99.996, 99.99), (100.0, 100.0)]:
            cache.clear()
            with mock.patch('core.views.requests.get', side_effect=self._fake_get({'availability_percent': raw})):
                data = self.client.get(self.url).json()
            self.assertEqual(data['availability']['percentage'], shown)

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
