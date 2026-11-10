"""Download a user-supplied image URL without letting it reach internal hosts.

The server runs inside the cluster, so a URL like http://<service>.svc/... or
http://169.254.169.254/ would otherwise be fetched and stored where the user
can read it back.

The host is resolved once per connection, every address must be public, and
the socket connects to that checked address. Re-resolving later (as a plain
requests.get would) lets a DNS answer change between check and connect.
"""
import ipaddress
import socket
import time
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import requests
from django.conf import settings
from PIL import Image as PILImage
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util.connection import create_connection

TIMEOUT = (5, 10)  # connect, per-read (seconds)
TOTAL_SECONDS = 30  # whole download
MAX_REDIRECTS = 3
EXTENSIONS = {'JPEG': 'jpg', 'PNG': 'png'}


class ImageFetchError(Exception):
    """The URL can't or mustn't be fetched; the message is safe to show."""


def public_addresses(host, port):
    """Resolve host; return its addresses, or raise if any of them isn't public."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise ImageFetchError('The image host could not be resolved.')
    addresses = []
    for info in infos:
        ip = info[4][0].split('%', 1)[0]
        address = ipaddress.ip_address(ip)
        if not address.is_global or address.is_multicast:
            raise ImageFetchError('That image URL points at a private address.')
        addresses.append(ip)
    return addresses


class _PublicConnectionMixin:
    def _new_conn(self):
        error = None
        for ip in public_addresses(self._dns_host, self.port):
            try:
                return create_connection((ip, self.port), self.timeout,
                                         source_address=self.source_address,
                                         socket_options=self.socket_options)
            except OSError as e:
                error = e
        raise error


class _PublicHTTPConnection(_PublicConnectionMixin, HTTPConnection):
    pass


class _PublicHTTPSConnection(_PublicConnectionMixin, HTTPSConnection):
    pass  # TLS still verifies the certificate against the hostname


class _PublicHTTPPool(HTTPConnectionPool):
    ConnectionCls = _PublicHTTPConnection


class _PublicHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _PublicHTTPSConnection


class _PublicAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {'http': _PublicHTTPPool, 'https': _PublicHTTPSPool}


def _session():
    session = requests.Session()
    session.trust_env = False  # ignore proxy env vars: they'd bypass the address check
    session.mount('http://', _PublicAdapter())
    session.mount('https://', _PublicAdapter())
    return session


def fetch_image(url):
    """Return (bytes, extension) for a public JPEG or PNG at url, following at most MAX_REDIRECTS."""
    deadline = time.monotonic() + TOTAL_SECONDS
    with _session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            if parts.scheme not in ('http', 'https') or not parts.hostname:
                raise ImageFetchError('Only http and https image URLs are allowed.')
            try:
                response = session.get(url, timeout=TIMEOUT, stream=True, allow_redirects=False)
            except requests.RequestException:
                raise ImageFetchError('The image could not be downloaded.')
            with response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('Location', ''))
                    continue
                if response.status_code != 200:
                    raise ImageFetchError('The image could not be downloaded.')
                data = _read_capped(response, deadline)
            return data, _image_extension(data)
    raise ImageFetchError('The image URL redirects too many times.')


def _read_capped(response, deadline):
    limit = settings.MAX_UPLOAD_SIZE
    chunks, size = [], 0
    try:
        for chunk in response.iter_content(64 * 1024):
            size += len(chunk)
            if size > limit:
                raise ImageFetchError(f'The image is larger than {limit // (1024 * 1024)}MB.')
            if time.monotonic() > deadline:
                raise ImageFetchError('The image took too long to download.')
            chunks.append(chunk)
    except requests.RequestException:
        raise ImageFetchError('The image could not be downloaded.')
    return b''.join(chunks)


def _image_extension(data):
    try:
        with PILImage.open(BytesIO(data)) as img:
            fmt = img.format
            img.verify()
    except Exception:
        raise ImageFetchError('The URL does not point at a valid image.')
    if fmt not in EXTENSIONS:
        raise ImageFetchError('Only JPEG and PNG images are allowed.')
    return EXTENSIONS[fmt]
