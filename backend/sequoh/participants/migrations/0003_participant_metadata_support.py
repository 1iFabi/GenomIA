import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('participants', '0002_observation'),
    ]

    operations = [
        migrations.CreateModel(
            name='ParticipantMetadata',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('name', models.CharField(max_length=255, null=True, blank=True)),
                ('questionary', models.JSONField(null=True, blank=True)),
                ('version', models.IntegerField(null=True, blank=True)),
                ('description', models.CharField(max_length=255, null=True, blank=True)),
                ('type', models.CharField(max_length=50, default='form_or_consent', db_default='form_or_consent')),
            ],
            options={'db_table': 'participant_metadata'},
        ),
        migrations.CreateModel(
            name='ParticipantMetadataLink',
            fields=[
                ('pk', models.CompositePrimaryKey('idm', 'idp', blank=True, editable=False, primary_key=True, serialize=False)),
                ('answer', models.JSONField(null=True, blank=True)),
                ('first_date', models.DateField(null=True, blank=True)),
                ('last_update', models.DateField(null=True, blank=True)),
                ('description', models.CharField(max_length=255, null=True, blank=True)),
                ('idm', models.ForeignKey(
                    to='participants.participantmetadata', on_delete=django.db.models.deletion.PROTECT,
                    db_column='idm', db_index=False, related_name='participant_links',
                )),
                ('idp', models.ForeignKey(
                    to='participants.participant', on_delete=django.db.models.deletion.PROTECT,
                    db_column='idp', db_index=False, related_name='metadata_links',
                )),
            ],
            options={'db_table': 'participant_2_meta'},
        ),
    ]
