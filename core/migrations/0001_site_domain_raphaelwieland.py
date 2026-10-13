"""
Point the Site record at raphaelwieland.com.

The sitemap and password-reset emails build absolute URLs from
Site(SITE_ID).domain. The blog now lives on raphaelwieland.com, and
wielandtech.com only redirects those paths there.
"""
from django.conf import settings
from django.db import migrations


def set_domain(domain):
    def forwards(apps, schema_editor):
        Site = apps.get_model('sites', 'Site')
        Site.objects.update_or_create(
            pk=settings.SITE_ID,
            defaults={'domain': domain},
            create_defaults={'domain': domain, 'name': domain},
        )
    return forwards


class Migration(migrations.Migration):

    dependencies = [
        ('sites', '0002_alter_domain_unique'),
    ]

    operations = [
        migrations.RunPython(
            set_domain('raphaelwieland.com'),
            set_domain('wielandtech.com'),
        ),
    ]
