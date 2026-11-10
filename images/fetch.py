"""Download a user-supplied image URL without letting it reach internal hosts.

The server runs inside the cluster, so a URL like http://<service>.svc/... or
http://169.254.169.254/ would otherwise be fetched and stored where the user
can read it back.
"""
import ipaddress
import socket
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import requests
from django.conf import settings
from PIL import Image as PILImage

TIMEOUT = (5, 10)  # connect, read (seconds)
MAX_REDIRECTS = 3
ALLOWED_FORMATS = {'JPEG', 'PNG'}


class ImageFetchError(Exception):
    """The URL can't or mustn't be fetched; the message is safe to show."""


def check_public_url(url):
    """Raise ImageFetchError unless url is http(s) and every address it resolves to is public."""
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ImageFetchError('Only http and https image URLs are allowed.')
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise ImageFetchError('The image host could not be resolved.')
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split('%', 1)[0])
        if not address.is_global or address.is_multicast:
            raise ImageFetchError('That image URL points at a private address.')


def fetch_image(url):
    """Return the bytes of a public JPEG or PNG at url, following at most MAX_REDIRECTS."""
    for _ in range(MAX_REDIRECTS + 1):
        check_public_url(url)
        try:
            response = requests.get(url, timeout=TIMEOUT, stream=True, allow_redirects=False)
        except requests.RequestException:
            raise ImageFetchError('The image could not be downloaded.')
        with response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get('Location', ''))
                continue
            if response.status_code != 200:
                raise ImageFetchError('The image could not be downloaded.')
            data = _read_capped(response)
        _check_image(data)
        return data
    raise ImageFetchError('The image URL redirects too many times.')


def _read_capped(response):
    limit = settings.MAX_UPLOAD_SIZE
    chunks, size = [], 0
    try:
        for chunk in response.iter_content(64 * 1024):
            size += len(chunk)
            if size > limit:
                raise ImageFetchError(f'The image is larger than {limit // (1024 * 1024)}MB.')
            chunks.append(chunk)
    except requests.RequestException:
        raise ImageFetchError('The image could not be downloaded.')
    return b''.join(chunks)


def _check_image(data):
    try:
        with PILImage.open(BytesIO(data)) as img:
            fmt = img.format
            img.verify()
    except Exception:
        raise ImageFetchError('The URL does not point at a valid image.')
    if fmt not in ALLOWED_FORMATS:
        raise ImageFetchError('Only JPEG and PNG images are allowed.')
