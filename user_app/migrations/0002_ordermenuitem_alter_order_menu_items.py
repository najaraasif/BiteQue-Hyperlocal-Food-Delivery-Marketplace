from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('merchant_app', '0001_initial'),
        ('user_app', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderMenuItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('menu_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='merchant_app.restaurantmenu')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='user_app.order')),
            ],
            options={
                'unique_together': {('order', 'menu_item')},
            },
        ),
        migrations.AddField(
            model_name='order',
            name='menu_items',
            field=models.ManyToManyField(
                through='user_app.OrderMenuItem',
                to='merchant_app.RestaurantMenu',
                related_name='orders'
            ),
        ),
    ]
