from django.conf import settings


def seo(request):
    """Canonical URL and indexability for core/base.html's SEO tags."""
    host = request.get_host().split(":")[0].lower()
    return {
        "site_url": settings.SITE_URL,
        "canonical_url": settings.SITE_URL + request.path,
        "seo_indexable": host in settings.SEO_INDEXED_HOSTS,
    }
