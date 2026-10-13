from django.test import TestCase, SimpleTestCase
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
