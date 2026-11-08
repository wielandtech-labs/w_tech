from django.core.cache import cache
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from unittest import mock
from core.sitemaps import StaticViewSitemap
from core.redis_client import RedisClient


class HomepageViewTests(TestCase):
    def test_homepage_status_code(self):
        response = self.client.get(reverse('core:core_home'))
        self.assertEqual(response.status_code, 200)

    def test_homepage_template_used(self):
        response = self.client.get(reverse('core:core_home'))
        self.assertTemplateUsed(response, 'core/index.html')


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


def _prom_response(result):
    response = mock.Mock(status_code=200)
    response.json.return_value = {'status': 'success', 'data': {'result': result}}
    return response


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class WeatherDataViewTests(TestCase):
    def setUp(self):
        cache.clear()

    @mock.patch('core.views.requests.get')
    def test_uses_newest_sample_across_pod_series(self, mock_get):
        # Old pod's series (stale) and new pod's series, as after an HA restart.
        mock_get.return_value = _prom_response([
            {'metric': {'pod': 'old'}, 'values': [[1000, '5.0'], [1100, '6.0']]},
            {'metric': {'pod': 'new'}, 'values': [[1300, '10.0']]},
        ])
        data = self.client.get(reverse('core:weather_data')).json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['temperature_c'], 10.0)
        self.assertEqual(data['temperature_f'], 50.0)
        self.assertEqual(data['as_of'], 1300)
        self.assertEqual(data['wind_direction_cardinal'], 'N')

    @mock.patch('core.views.requests.get')
    def test_no_reading_in_last_hour(self, mock_get):
        mock_get.return_value = _prom_response([])
        data = self.client.get(reverse('core:weather_data')).json()
        self.assertEqual(data, {'status': 'no_data'})
