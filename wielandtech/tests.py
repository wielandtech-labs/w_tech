"""
Tests for custom middleware and security settings.
"""
import os
import subprocess
import sys

from django.conf import settings
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from wielandtech.middleware import (
    InternalAdminCookieMiddleware,
    SecurityHeadersMiddleware,
    WwwRedirectMiddleware,
)


class InternalAdminCookieMiddlewareTests(SimpleTestCase):
    def _get_response_with_secure_cookies(self, request):
        response = HttpResponse()
        response.set_cookie(settings.SESSION_COOKIE_NAME, 'session-value', secure=True)
        response.set_cookie(settings.CSRF_COOKIE_NAME, 'csrf-value', secure=True)
        return response

    def _run(self, host, secure, get_response=None):
        middleware = InternalAdminCookieMiddleware(
            get_response or self._get_response_with_secure_cookies
        )
        request = RequestFactory().get('/admin/login/', HTTP_HOST=host, secure=secure)
        return middleware(request)

    def assert_secure_flags(self, response, expected):
        for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
            self.assertEqual(bool(response.cookies[name]['secure']), expected, name)

    def test_strips_secure_flag_for_http_on_internal_host(self):
        response = self._run('wielandtech.k8s.local', secure=False)
        self.assert_secure_flags(response, expected=False)

    def test_keeps_secure_flag_for_https_on_internal_host(self):
        response = self._run('wielandtech.k8s.local', secure=True)
        self.assert_secure_flags(response, expected=True)

    def test_keeps_secure_flag_for_public_host(self):
        for secure in (False, True):
            response = self._run('raphaelwieland.com', secure=secure)
            self.assert_secure_flags(response, expected=True)

    def test_response_without_cookies_passes_through(self):
        response = self._run(
            'wielandtech.k8s.local', secure=False,
            get_response=lambda request: HttpResponse(),
        )
        self.assertEqual(len(response.cookies), 0)


class SecurityHeadersMiddlewareTests(SimpleTestCase):
    def _run(self, host):
        middleware = SecurityHeadersMiddleware(lambda request: HttpResponse())
        request = RequestFactory().get('/', HTTP_HOST=host)
        return middleware(request)

    def test_sets_csp_on_public_hosts(self):
        for host in ('raphaelwieland.com', 'www.raphaelwieland.com'):
            with self.subTest(host=host):
                self.assertIn('Content-Security-Policy', self._run(host))

    def test_ignores_port_when_matching_host(self):
        self.assertIn('Content-Security-Policy', self._run('raphaelwieland.com:443'))

    def test_retired_portfolio_host_is_not_served(self):
        # wielandtech.com is served by w_portfolio now, not by this app.
        from wielandtech.middleware import CSP_HOSTS
        for host in ('wielandtech.com', 'www.wielandtech.com'):
            with self.subTest(host=host):
                self.assertNotIn(host, CSP_HOSTS)
                self.assertNotIn(host, settings.ALLOWED_HOSTS)

    def test_omits_csp_on_internal_host(self):
        self.assertNotIn('Content-Security-Policy', self._run('wielandtech.k8s.local'))

    def test_always_sets_baseline_headers(self):
        response = self._run('wielandtech.k8s.local')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertEqual(response['Referrer-Policy'], 'strict-origin-when-cross-origin')



class WwwRedirectMiddlewareTests(SimpleTestCase):
    def _run(self, host, path='/', method='get'):
        middleware = WwwRedirectMiddleware(lambda request: HttpResponse('served'))
        request = getattr(RequestFactory(), method)(path, HTTP_HOST=host)
        return middleware(request)

    def test_www_redirects_to_apex_keeping_path_and_query(self):
        response = self._run('www.raphaelwieland.com', '/blog/?page=2')
        self.assertEqual(response.status_code, 308)
        self.assertEqual(response['Location'], 'https://raphaelwieland.com/blog/?page=2')

    def test_post_keeps_its_method(self):
        self.assertEqual(self._run('www.raphaelwieland.com', method='post').status_code, 308)

    def test_apex_is_served(self):
        self.assertEqual(self._run('raphaelwieland.com').content, b'served')

    def test_unknown_www_host_is_rejected_not_redirected(self):
        from django.core.exceptions import DisallowedHost
        with self.assertRaises(DisallowedHost):
            self._run('www.evil.example')


class SecretKeySettingTests(SimpleTestCase):
    def _import_settings(self, **env):
        # A fresh interpreter, since settings are evaluated once per process.
        # An empty DJANGO_SECRET_KEY counts as unset, and load_dotenv() never
        # overrides a variable that is already present, so a local .env can't
        # leak in.
        return subprocess.run(
            [sys.executable, '-c', 'import wielandtech.settings'],
            cwd=settings.BASE_DIR,
            env={**os.environ, 'DJANGO_SECRET_KEY': '', **env},
            capture_output=True,
            text=True,
        )

    def test_startup_fails_without_secret_key_when_debug_off(self):
        result = self._import_settings(DEBUG='False')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY must be set', result.stderr)

    def test_debug_allows_missing_secret_key(self):
        result = self._import_settings(DEBUG='True')
        self.assertEqual(result.returncode, 0, result.stderr)


class CsrfTrustedOriginsTests(TestCase):
    def test_trusted_origins_are_https_only(self):
        for origin in settings.CSRF_TRUSTED_ORIGINS:
            self.assertTrue(origin.startswith('https://'), origin)

    def test_same_origin_http_post_on_lan_host_passes_csrf(self):
        # Plain-http admin login on wielandtech.k8s.local needs no trusted
        # origin: Django accepts an Origin that matches the request's own.
        client = Client(enforce_csrf_checks=True)
        host = 'wielandtech.k8s.local'
        client.get(reverse('login'), HTTP_HOST=host)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        resp = client.post(reverse('login'), {'csrfmiddlewaretoken': token},
                           HTTP_HOST=host, HTTP_ORIGIN=f'http://{host}')
        # 200: CSRF passed and the login form re-renders with its errors.
        self.assertEqual(resp.status_code, 200)

    def test_cross_origin_http_post_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse('login'), HTTP_HOST='raphaelwieland.com')
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        resp = client.post(reverse('login'), {'csrfmiddlewaretoken': token},
                           HTTP_HOST='raphaelwieland.com',
                           HTTP_ORIGIN='http://dev.wielandtech.com')
        self.assertEqual(resp.status_code, 403)
