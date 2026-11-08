"""JSON-LD structured data for search engines.

Each tag returns a complete <script type="application/ld+json"> element. The
JSON is escaped so post titles or bodies can't close the script element.
"""

import json

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()

PERSON = {
    "@type": "Person",
    "@id": "https://raphaelwieland.com/#person",
    "name": "Raphael Wieland",
    "url": "https://raphaelwieland.com/",
    "jobTitle": "Software and infrastructure engineer",
    "worksFor": {
        "@type": "Organization",
        "name": "VLAN Technology Services, LLC",
        "alternateName": "WielandTech",
        "url": "https://wielandtech.com/",
    },
    "sameAs": [
        "https://wielandtech.com/",
        "https://github.com/wielandtech",
        "https://www.linkedin.com/in/raphael-wieland/",
    ],
}


def _script(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Neutralise "</script>" and HTML comment openers inside strings.
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


def _abs(path):
    return path if path.startswith("http") else settings.SITE_URL + path


@register.simple_tag
def person_jsonld():
    site = {
        "@type": "WebSite",
        "@id": "https://raphaelwieland.com/#website",
        "url": "https://raphaelwieland.com/",
        "name": "WielandTech",
        "publisher": {"@id": PERSON["@id"]},
    }
    person = dict(PERSON, image=_abs(static("img/profile.png")))
    return _script({"@context": "https://schema.org", "@graph": [site, person]})


@register.simple_tag
def post_jsonld(post, description=""):
    url = _abs(post.get_absolute_url())
    data = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "@id": url + "#post",
        "mainEntityOfPage": url,
        "url": url,
        "headline": post.title[:110],
        "description": description,
        "datePublished": post.publish.isoformat(),
        "dateModified": post.updated.isoformat(),
        "author": {"@id": PERSON["@id"], "@type": "Person", "name": "Raphael Wieland", "url": PERSON["url"]},
        "publisher": {"@id": PERSON["@id"]},
        "keywords": [t.name for t in post.tags.all()],
        "isPartOf": {"@type": "Blog", "name": "WielandTech Blog", "url": _abs("/blog/")},
    }
    return _script(data)
