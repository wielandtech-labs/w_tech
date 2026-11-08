import math

import markdown

from django import template
from django.db.models import Count
from django.utils.safestring import mark_safe

from ..models import Post

register = template.Library()


@register.filter(name='markdown')
def markdown_format(text):
    return mark_safe(markdown.markdown(
        text,
        extensions=['fenced_code', 'codehilite'],
        extension_configs={'codehilite': {'guess_lang': False}},
    ))






@register.simple_tag
def get_most_commented_posts(count=5):
    return Post.published.annotate(total_comments=Count('comments')).order_by('-total_comments')[:count]


@register.inclusion_tag('blog/post/latest_posts.html')
def show_latest_posts(count=5):
    latest_posts = Post.published.order_by('-publish')[:count]
    return {'latest_posts': latest_posts}


@register.simple_tag
def total_posts():
    return Post.published.count()


@register.filter(name='plain_summary')
def plain_summary(text, length=160):
    """Markdown body -> plain-text summary for meta descriptions.

    Skips code blocks and headings, then cuts at a word boundary.
    """
    import html as html_lib
    import re

    from django.utils.html import strip_tags

    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    html = markdown.markdown(text)
    html = re.sub(r"<h[1-6][^>]*>.*?</h[1-6]>", " ", html, flags=re.S)
    plain = " ".join(html_lib.unescape(strip_tags(html)).split())
    length = int(length)
    if len(plain) <= length:
        return plain
    cut = plain[: length - 1].rsplit(" ", 1)[0].rstrip(",.;:")
    return cut + "…"


@register.filter(name='reading_time')
def reading_time(text, wpm=200):
    """Estimated minutes to read `text` at ~200 words/min, at least 1."""
    words = len((text or "").split())
    return max(1, math.ceil(words / int(wpm)))
