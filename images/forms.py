from django import forms
from django.core.files.base import ContentFile
from django.utils.text import slugify
from django.conf import settings
from .fetch import fetch_image
from .models import Image


class ImageCreateForm(forms.ModelForm):
    class Meta:
        model = Image
        fields = ('title', 'url', 'description')
        widgets = {
            'url': forms.HiddenInput,
        }

    def clean_url(self):
        url = self.cleaned_data['url']

        valid_extensions = ['jpg', 'jpeg', 'png']
        extension = url.rsplit('.', 1)[1].lower()
        if extension not in valid_extensions:
            raise forms.ValidationError('The given URL does not match valid image extensions.')
        return url

    def save(self, force_insert=False,
             force_update=False,
             commit=True):
        image = super().save(commit=False)

        # download image from the given URL (raises ImageFetchError)
        data, extension = fetch_image(self.cleaned_data['url'])
        image.image.save(f'{slugify(image.title)}.{extension}', ContentFile(data), save=False)
        if commit:
            image.save()
        return image


class ImageUploadForm(forms.ModelForm):
    class Meta:
        model = Image
        fields = ('title', 'url', 'image', 'description')
        widgets = {
            'url': forms.URLInput(attrs={'placeholder': 'Enter image URL (optional)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['url'].required = False
        self.fields['image'].required = False

    def clean(self):
        cleaned_data = super().clean()
        url = cleaned_data.get('url')
        image = cleaned_data.get('image')

        if not url and not image:
            raise forms.ValidationError('Please provide either an image URL or upload an image file.')

        if url and image:
            raise forms.ValidationError('Please provide either a URL or upload a file, not both.')

        return cleaned_data

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.size > settings.MAX_UPLOAD_SIZE:
                raise forms.ValidationError(f'Image file too large ( > {settings.MAX_UPLOAD_SIZE/1024/1024}MB )')
        return image

    def clean_url(self):
        url = self.cleaned_data.get('url')
        if url:
            valid_extensions = ['jpg', 'jpeg', 'png']
            extension = url.rsplit('.', 1)[1].lower()
            if extension not in valid_extensions:
                raise forms.ValidationError('The given URL does not match valid image extensions.')
        return url

    def save(self, force_insert=False, force_update=False, commit=True):
        image = super().save(commit=False)

        if self.cleaned_data.get('url'):
            data, extension = fetch_image(self.cleaned_data['url'])  # raises ImageFetchError
            image.image.save(f'{slugify(image.title)}.{extension}', ContentFile(data), save=False)

        if commit:
            image.save()
        return image
