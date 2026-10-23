from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    # settings.CACHES is a DatabaseCache shared by every worker (throttle counters); migrate creates it.
    call_command('createcachetable', database=schema_editor.connection.alias)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_token_version_and_revoked_token_index'),
    ]

    operations = [
        migrations.RunPython(create_cache_table, migrations.RunPython.noop),
    ]
