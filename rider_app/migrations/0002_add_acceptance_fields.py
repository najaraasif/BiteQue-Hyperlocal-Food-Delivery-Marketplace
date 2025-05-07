from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('rider_app', '0001_initial'),  # Replace with your last migration
    ]

    operations = [
        migrations.AddField(
            model_name='rider',
            name='accepted_assignments',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='rider',
            name='total_assignments',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='rider',
            name='acceptance_rate',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='rider',
            name='last_rate_update',
            field=models.DateTimeField(auto_now=True),
        ),
    ]