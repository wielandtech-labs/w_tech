from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    protocol = 'https'
    changefreq = 'monthly'
    # The homepage first; the rest are public pages worth indexing.
    pages = ['core:core_home', 'blog:post_list', 'core:homelab', 'core:weather', 'core:contact', 'images:list']

    def items(self):
        return self.pages

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return 1.0 if item == 'core:core_home' else 0.6
