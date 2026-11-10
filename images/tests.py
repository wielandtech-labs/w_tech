import socket
from io import BytesIO

from PIL import Image as PILImage
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch, MagicMock
from .models import Image
from .fetch import ImageFetchError, fetch_image
from .forms import ImageCreateForm, ImageUploadForm
from django.core.files.uploadedfile import SimpleUploadedFile

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


def resolves_to(*addresses):
    """Patch DNS so every host resolves to the given addresses."""
    infos = [(socket.AF_INET6 if ':' in a else socket.AF_INET, socket.SOCK_STREAM, 6, '', (a, 80))
             for a in addresses]
    return patch('images.fetch.socket.getaddrinfo', return_value=infos)


def png_bytes():
    buf = BytesIO()
    PILImage.new('RGB', (2, 2), 'red').save(buf, format='PNG')
    return buf.getvalue()


def fake_response(status=200, body=b'', location=None):
    response = MagicMock()
    response.status_code = status
    response.is_redirect = location is not None
    response.headers = {'Location': location} if location else {}
    response.iter_content.return_value = [body]
    response.__enter__.return_value = response
    return response


class ImageFormTests(TestCase):
    def test_image_create_form_valid(self):
        with resolves_to('93.184.215.14'):
            form = ImageCreateForm(data={'title': 'Test', 'url': 'http://example.com/image.jpg', 'description': 'desc'})
            self.assertTrue(form.is_valid())

    def test_image_create_form_rejects_internal_addresses(self):
        for address in ('127.0.0.1', '10.43.0.10', '192.168.70.240', '169.254.169.254', '::1', 'fd00::1'):
            with self.subTest(address=address), resolves_to(address):
                form = ImageCreateForm(data={'title': 'T', 'url': 'http://internal.example/x.png', 'description': ''})
                self.assertFalse(form.is_valid())
                self.assertIn('private address', str(form.errors['url']))

    def test_image_create_form_rejects_mixed_public_and_private_dns(self):
        with resolves_to('93.184.215.14', '10.0.0.5'):
            form = ImageCreateForm(data={'title': 'T', 'url': 'http://example.com/x.png', 'description': ''})
            self.assertFalse(form.is_valid())

    def test_image_upload_form_rejects_internal_url(self):
        with resolves_to('10.42.0.7'):
            form = ImageUploadForm(data={'title': 'T', 'url': 'http://svc.cluster.local/x.jpg', 'description': ''})
            self.assertFalse(form.is_valid())
            self.assertIn('url', form.errors)

    def test_image_upload_form_rejects_ftp(self):
        form = ImageUploadForm(data={'title': 'T', 'url': 'ftp://example.com/x.jpg', 'description': ''})
        self.assertFalse(form.is_valid())

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


class FetchImageTests(TestCase):
    def test_returns_png_bytes(self):
        data = png_bytes()
        with resolves_to('93.184.215.14'), \
                patch('images.fetch.requests.get', return_value=fake_response(body=data)) as get:
            self.assertEqual(fetch_image('https://example.com/a.png'), data)
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertIsNotNone(get.call_args.kwargs['timeout'])

    def test_redirect_to_internal_host_is_refused(self):
        responses = [fake_response(status=302, location='http://10.43.0.1/secret.png')]
        with patch('images.fetch.requests.get', side_effect=responses), \
                patch('images.fetch.socket.getaddrinfo', side_effect=[
                    resolves_to('93.184.215.14').kwargs['return_value'],
                    resolves_to('10.43.0.1').kwargs['return_value'],
                ]):
            with self.assertRaisesMessage(ImageFetchError, 'private address'):
                fetch_image('https://example.com/a.png')

    def test_too_many_redirects(self):
        loop = [fake_response(status=302, location='https://example.com/a.png') for _ in range(5)]
        with resolves_to('93.184.215.14'), patch('images.fetch.requests.get', side_effect=loop):
            with self.assertRaisesMessage(ImageFetchError, 'too many times'):
                fetch_image('https://example.com/a.png')

    @override_settings(MAX_UPLOAD_SIZE=10)
    def test_oversize_body_is_refused(self):
        with resolves_to('93.184.215.14'), \
                patch('images.fetch.requests.get', return_value=fake_response(body=b'x' * 11)):
            with self.assertRaisesMessage(ImageFetchError, 'larger than'):
                fetch_image('https://example.com/a.png')

    def test_non_image_body_is_refused(self):
        with resolves_to('93.184.215.14'), \
                patch('images.fetch.requests.get', return_value=fake_response(body=b'<html>secret</html>')):
            with self.assertRaisesMessage(ImageFetchError, 'valid image'):
                fetch_image('https://example.com/a.png')

    def test_non_200_is_refused(self):
        with resolves_to('93.184.215.14'), \
                patch('images.fetch.requests.get', return_value=fake_response(status=404)):
            with self.assertRaises(ImageFetchError):
                fetch_image('https://example.com/a.png')


class ImageCreateFetchErrorViewTests(TestCase):
    def test_fetch_error_shows_form_error_not_500(self):
        user = User.objects.create_user(username='u', password='p')
        self.client.force_login(user)
        with resolves_to('93.184.215.14'), \
                patch('images.fetch.requests.get', return_value=fake_response(body=b'not an image')):
            response = self.client.post(reverse('images:create'),
                                        {'title': 'T', 'url': 'https://example.com/a.png', 'description': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'valid image')
        self.assertFalse(Image.objects.filter(title='T').exists())
