import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch, MagicMock
from .models import Image
from .forms import ImageCreateForm, ImageUploadForm
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image as PILImage
from . import fetch
from .fetch import ImageFetchError, fetch_image

User = get_user_model()


class ImageModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='user1', password='pass')

    def test_slug_is_generated_on_save(self):
        img = Image.objects.create(user=self.user, title='Test Image', url='http://example.com/test.jpg', image='test.jpg')
        self.assertEqual(img.slug, 'test-image')

    def test_get_absolute_url(self):
        img = Image.objects.create(user=self.user, title='Test', url='http://example.com/test.jpg', image='test.jpg')
        self.assertIn(str(img.id), img.get_absolute_url())
        self.assertIn(img.slug, img.get_absolute_url())


class ImageFormTests(TestCase):
    def test_image_create_form_valid(self):
        form = ImageCreateForm(data={'title': 'Test', 'url': 'http://example.com/image.jpg', 'description': 'desc'})
        self.assertTrue(form.is_valid())

    def test_image_create_form_invalid_extension(self):
        form = ImageCreateForm(data={'title': 'Test', 'url': 'http://example.com/image.txt', 'description': 'desc'})
        self.assertFalse(form.is_valid())

    def test_image_upload_form_mutual_exclusion(self):
        form = ImageUploadForm(data={'title': 'Test', 'description': 'desc'})
        self.assertFalse(form.is_valid())


class ImageViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user1', password='pass')
        self.image = Image.objects.create(user=self.user, title='Title', url='http://example.com/test.jpg', image='test.jpg')

    def test_image_detail_view(self):
        url = reverse('images:detail', args=[self.image.id, self.image.slug])
        with patch('images.views.get_redis') as mock_redis:
            mock_redis.return_value = MagicMock()
            self.client.force_login(self.user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Title')

    def test_image_like_view(self):
        url = reverse('images:like')
        self.client.force_login(self.user)
        response = self.client.post(url, {'id': self.image.id, 'action': 'like'},
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'status': 'ok'})

    def test_image_create_view_get(self):
        url = reverse('images:create')
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_image_upload_view_get(self):
        url = reverse('images:upload')
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class PublicImageListTests(TestCase):
    def setUp(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.member = User.objects.create_user(username='member', password='pass')
        self.staff_image = Image.objects.create(user=staff, title='Staff Photo', url='http://example.com/a.jpg', image='a.jpg')
        self.member_image = Image.objects.create(user=self.member, title='Member Photo', url='http://example.com/b.jpg', image='b.jpg')

    def test_logged_out_list_shows_only_staff_images(self):
        response = self.client.get(reverse('images:list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['most_liked']), [self.staff_image])
        self.assertContains(response, 'Staff Photo')
        self.assertNotContains(response, 'Member Photo')
        self.assertContains(response, 'Log in to like and comment')
        self.assertContains(response, '/account/login/?next=/images/')
        self.assertNotContains(response, self.staff_image.get_absolute_url())

    def test_logged_out_list_hides_inactive_staff_images(self):
        former = User.objects.create_user(username='former', password='pass', is_staff=True, is_active=False)
        Image.objects.create(user=former, title='Former Photo', url='http://example.com/c.jpg', image='c.jpg')
        response = self.client.get(reverse('images:list'))
        self.assertNotContains(response, 'Former Photo')

    def test_logged_out_ajax_page_shows_only_staff_images(self):
        response = self.client.get(reverse('images:list'), {'page': 1},
                                   HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Staff Photo')
        self.assertNotContains(response, 'Member Photo')
        empty = self.client.get(reverse('images:list'), {'page': 2},
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(empty.content, b'')

    def test_logged_in_list_shows_all_images(self):
        self.client.force_login(self.member)
        with patch('images.views.get_redis') as mock_redis:
            mock_redis.return_value.zrange.return_value = []
            response = self.client.get(reverse('images:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Staff Photo')
        self.assertContains(response, 'Member Photo')
        self.assertNotContains(response, 'Log in to like and comment')

    def test_logged_in_list_survives_redis_outage(self):
        self.client.force_login(self.member)
        with patch('images.views.get_redis', return_value=None):
            response = self.client.get(reverse('images:list'))
        self.assertEqual(response.status_code, 200)

    def test_protected_views_redirect_logged_out(self):
        urls = [
            reverse('images:detail', args=[self.staff_image.id, self.staff_image.slug]),
            reverse('images:upload'),
            reverse('images:create'),
            reverse('images:ranking'),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith('/account/login/'))
        response = self.client.post(reverse('images:like'), {'id': self.staff_image.id, 'action': 'like'},
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/account/login/'))
        self.assertFalse(self.staff_image.users_like.exists())


def addrinfo(*addresses):
    return [(socket.AF_INET6 if ':' in a else socket.AF_INET, socket.SOCK_STREAM, 6, '', (a, 80))
            for a in addresses]


def png_bytes():
    buf = BytesIO()
    PILImage.new('RGB', (2, 2), 'red').save(buf, format='PNG')
    return buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        status, headers, body = self.routes.get(self.path, (404, {}, b''))
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class FetchImageTests(TestCase):
    """Real HTTP against a local server; "img.test" is pinned to 127.0.0.1."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        _Handler.routes = {
            '/a.png': (200, {}, png_bytes()),
            '/page.png': (200, {}, b'<html>secret</html>'),
            '/big.png': (200, {}, b'x' * 64),
            '/to-internal.png': (302, {'Location': 'http://internal.test/x.png'}, b''),
            '/loop.png': (302, {'Location': '/loop.png'}, b''),
        }

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        super().tearDownClass()

    def url(self, path):
        return f'http://img.test:{self.port}{path}'

    def setUp(self):
        real = fetch.public_addresses

        def resolve(host, port):
            if host == 'img.test':
                return ['127.0.0.1']
            with patch('images.fetch.socket.getaddrinfo', return_value=addrinfo('10.43.0.1')):
                return real(host, port)
        patcher = patch('images.fetch.public_addresses', side_effect=resolve)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_returns_png_and_real_extension(self):
        data, ext = fetch_image(self.url('/a.png'))
        self.assertEqual(data, png_bytes())
        self.assertEqual(ext, 'png')

    def test_redirect_to_internal_host_is_refused(self):
        with self.assertRaisesMessage(ImageFetchError, 'private address'):
            fetch_image(self.url('/to-internal.png'))

    def test_too_many_redirects(self):
        with self.assertRaisesMessage(ImageFetchError, 'too many times'):
            fetch_image(self.url('/loop.png'))

    @override_settings(MAX_UPLOAD_SIZE=10)
    def test_oversize_body_is_refused(self):
        with self.assertRaisesMessage(ImageFetchError, 'larger than'):
            fetch_image(self.url('/big.png'))

    def test_non_image_body_is_refused(self):
        with self.assertRaisesMessage(ImageFetchError, 'valid image'):
            fetch_image(self.url('/page.png'))

    def test_non_200_is_refused(self):
        with self.assertRaises(ImageFetchError):
            fetch_image(self.url('/missing.png'))

    def test_ftp_is_refused(self):
        with self.assertRaisesMessage(ImageFetchError, 'Only http and https'):
            fetch_image('ftp://img.test/a.png')

    def test_bad_port_is_a_fetch_error(self):
        with self.assertRaises(ImageFetchError):
            fetch_image('http://img.test:99999/a.png')

    def test_proxy_env_is_ignored(self):
        proxy = 'http://10.43.0.9:3128'
        with patch.dict('os.environ', {'HTTP_PROXY': proxy, 'http_proxy': proxy}):
            data, _ = fetch_image(self.url('/a.png'))
        self.assertEqual(data, png_bytes())


class PublicAddressTests(TestCase):
    def test_internal_addresses_are_refused(self):
        for address in ('127.0.0.1', '10.43.0.10', '192.168.70.240', '169.254.169.254', '::1', 'fd00::1',
                        '::ffff:10.0.0.1'):
            with self.subTest(address=address), \
                    patch('images.fetch.socket.getaddrinfo', return_value=addrinfo(address)):
                with self.assertRaisesMessage(ImageFetchError, 'private address'):
                    fetch.public_addresses('internal.example', 80)

    def test_one_private_answer_is_enough_to_refuse(self):
        with patch('images.fetch.socket.getaddrinfo', return_value=addrinfo('93.184.215.14', '10.0.0.5')):
            with self.assertRaises(ImageFetchError):
                fetch.public_addresses('example.com', 80)

    def test_public_address_is_allowed(self):
        with patch('images.fetch.socket.getaddrinfo', return_value=addrinfo('93.184.215.14')):
            self.assertEqual(fetch.public_addresses('example.com', 80), ['93.184.215.14'])

    def test_connection_to_private_dns_answer_never_opens(self):
        """The pinned connection refuses before any socket is opened."""
        with patch('images.fetch.socket.getaddrinfo', return_value=addrinfo('10.43.0.10')), \
                patch('images.fetch.create_connection') as connect:
            with self.assertRaisesMessage(ImageFetchError, 'private address'):
                fetch_image('http://rebind.example/a.png')
        connect.assert_not_called()


class ImageFetchErrorViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', password='p')
        self.client.force_login(self.user)

    def test_create_with_internal_url_shows_form_error(self):
        with patch('images.fetch.socket.getaddrinfo', return_value=addrinfo('10.43.0.10')):
            response = self.client.post(reverse('images:create'),
                                        {'title': 'T', 'url': 'http://svc.example/a.png', 'description': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'private address')
        self.assertFalse(Image.objects.filter(title='T').exists())

    def test_upload_with_internal_url_shows_form_error(self):
        with patch('images.fetch.socket.getaddrinfo', return_value=addrinfo('10.43.0.10')):
            response = self.client.post(reverse('images:upload'),
                                        {'title': 'U', 'url': 'http://svc.example/a.png', 'description': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'private address')
        self.assertFalse(Image.objects.filter(title='U').exists())

    def test_bookmarklet_get_does_no_dns_lookup(self):
        with patch('images.fetch.socket.getaddrinfo') as resolve:
            response = self.client.get(reverse('images:create'),
                                       {'title': 'T', 'url': 'http://anything.example/a.png'})
        self.assertEqual(response.status_code, 200)
        resolve.assert_not_called()
