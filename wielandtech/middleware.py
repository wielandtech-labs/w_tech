"""
Custom middleware for security and access control.
"""
from django.http import HttpResponseForbidden
from django.conf import settings

# Hosts allowed to reach the Django admin (LAN-only access paths).
INTERNAL_ADMIN_HOSTS = [
    'wielandtech.k8s.local',
    '127.0.0.1',
    'localhost',
]


class AllowMetricsEndpointMiddleware:
    """
    Allow /metrics endpoint to bypass ALLOWED_HOSTS validation.
    This is necessary for Prometheus scraping which connects via pod IP.
    Must be placed BEFORE SecurityMiddleware in MIDDLEWARE list.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # For the metrics endpoint, set a flag to bypass host validation
        # by temporarily allowing any host for this specific path
        if request.path == '/metrics' or request.path == '/metrics/':
            # Set the HTTP_HOST to an allowed value for metrics requests
            # This allows Prometheus to scrape via pod IP
            request.META['HTTP_HOST'] = 'localhost'
        
        response = self.get_response(request)
        return response


class RestrictAdminMiddleware:
    """
    Restrict Django admin access to internal domains only.
    Public access to /admin/ is blocked.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.allowed_admin_hosts = INTERNAL_ADMIN_HOSTS

    def __call__(self, request):
        # Check if accessing admin URLs
        if request.path.startswith('/admin/'):
            host = request.get_host().split(':')[0]  # Remove port if present
            
            # Block access if not from allowed internal domain
            if host not in self.allowed_admin_hosts and not settings.DEBUG:
                return HttpResponseForbidden(
                    '<h1>403 Forbidden</h1>'
                    '<p>Admin access is restricted to internal network only.</p>'
                )
        
        response = self.get_response(request)
        return response


class InternalAdminCookieMiddleware:
    """
    Strip the Secure flag from session/CSRF cookies on plain-HTTP requests
    to internal admin hosts, so admin login works at
    http://wielandtech.k8s.local/ while public hosts keep Secure cookies.
    Must be placed BEFORE SessionMiddleware and CsrfViewMiddleware in
    MIDDLEWARE so it processes the response after they set their cookies.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        host = request.get_host().split(':')[0]
        if not request.is_secure() and host in INTERNAL_ADMIN_HOSTS:
            for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
                if name in response.cookies:
                    # An empty value removes the Secure attribute
                    response.cookies[name]['secure'] = ''

        return response


class SecurityHeadersMiddleware:
    """
    Add additional security headers for public-facing traffic.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Add CSP for public domains only
        host = request.get_host().split(':')[0]
        if host in ['wielandtech.com', 'www.wielandtech.com']:
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
                "https://ajax.googleapis.com https://www.googletagmanager.com "
                "https://cdn.jsdelivr.net https://www.google.com https://www.gstatic.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "frame-src 'self' https://www.google.com https://www.gstatic.com; "
                "connect-src 'self' https://www.google-analytics.com https://cdn.jsdelivr.net "
                "https://www.google.com https://www.gstatic.com;"
            )
        
        return response

