from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch, MagicMock
from .models import Image
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
