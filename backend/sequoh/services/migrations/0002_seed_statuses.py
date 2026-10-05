from django.db import migrations


PURCHASE_STATUSES = {
    'PENDING': 'Pending',
    'PAID': 'Paid',
    'CANCELLED': 'Cancelled',
    'REFUNDED': 'Refunded',
}
SERVICE_STATUSES = {
    'WAITING_SAMPLE': 'Waiting for sample',
    'SAMPLE_RECEIVED': 'Sample received',
    'PROCESSING': 'Processing',
    'COMPLETED': 'Completed',
}


def seed_statuses(apps, schema_editor):
    alias = schema_editor.connection.alias
    for model_name, statuses in (
        ('PurchaseStatus', PURCHASE_STATUSES),
        ('ServiceStatus', SERVICE_STATUSES),
    ):
        model = apps.get_model('services', model_name)
        for code, name in statuses.items():
            model.objects.using(alias).get_or_create(code=code, defaults={'name': name})


class Migration(migrations.Migration):
    dependencies = [
        ('services', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_statuses, migrations.RunPython.noop),
    ]
