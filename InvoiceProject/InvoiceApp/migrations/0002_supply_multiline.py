from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_supply_data_forward(apps, schema_editor):
    """
    Pour chaque Supply existant (mono-produit), crée la SupplyItem
    correspondante afin de ne perdre aucune donnée de production.
    """
    Supply = apps.get_model('InvoiceApp', 'Supply')
    SupplyItem = apps.get_model('InvoiceApp', 'SupplyItem')

    for supply in Supply.objects.all():
        quantity = supply.quantity or 0
        unit_price = supply.unit_price or Decimal('0.00')
        SupplyItem.objects.create(
            supply=supply,
            product=supply.product,
            quantity=quantity,
            unit_price=unit_price,
            total_price=Decimal(quantity) * Decimal(unit_price),
            currency=supply.currency,
        )


def migrate_supply_data_backward(apps, schema_editor):
    """
    Reconstitue les champs mono-produit de Supply à partir de la première
    SupplyItem, pour permettre un retour en arrière (migrate vers 0001).
    """
    Supply = apps.get_model('InvoiceApp', 'Supply')

    for supply in Supply.objects.all():
        first_item = supply.supply_items.order_by('id').first()
        if first_item:
            supply.product_id = first_item.product_id
            supply.quantity = first_item.quantity
            supply.unit_price = first_item.unit_price
            supply.save(update_fields=['product', 'quantity', 'unit_price'])


class Migration(migrations.Migration):

    dependencies = [
        ('InvoiceApp', '0001_initial'),
    ]

    operations = [
        # 1. Crée le nouveau modèle SupplyItem
        migrations.CreateModel(
            name='SupplyItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1, verbose_name='Quantité')),
                ('unit_price', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10, verbose_name='Prix unitaire')),
                ('total_price', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10, verbose_name='Prix total')),
                ('currency', models.CharField(choices=[('EUR', 'Euro (€)'), ('USD', 'Dollar US ($)'), ('XOF', 'Franc CFA (FCFA)')], default='EUR', max_length=3, verbose_name='Devise')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='supply_items', to='InvoiceApp.product', verbose_name='Produit')),
                ('supply', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='supply_items', to='InvoiceApp.supply', verbose_name='Approvisionnement')),
            ],
            options={
                'verbose_name': "Ligne d'approvisionnement",
                'verbose_name_plural': "Lignes d'approvisionnement",
            },
        ),

        # 2. Rend total_price/currency non bloquants avec une valeur par défaut,
        #    nécessaire avant de pouvoir déduire les anciennes lignes.
        migrations.AlterField(
            model_name='supply',
            name='total_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10, verbose_name='Prix total'),
        ),

        # 3. Migration de données : une SupplyItem par Supply existant
        migrations.RunPython(migrate_supply_data_forward, migrate_supply_data_backward),

        # 4. Retire les anciens champs mono-produit de Supply, devenu un en-tête
        migrations.RemoveField(
            model_name='supply',
            name='product',
        ),
        migrations.RemoveField(
            model_name='supply',
            name='quantity',
        ),
        migrations.RemoveField(
            model_name='supply',
            name='unit_price',
        ),
    ]