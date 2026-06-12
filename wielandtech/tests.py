"""
Tests for custom middleware.
"""
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from wielandtech.middleware import InternalAdminCookieMiddleware


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
            response = self._run('wielandtech.com', secure=secure)
            self.assert_secure_flags(response, expected=True)

    def test_response_without_cookies_passes_through(self):
        response = self._run(
            'wielandtech.k8s.local', secure=False,
            get_response=lambda request: HttpResponse(),
        )
        self.assertEqual(len(response.cookies), 0)
