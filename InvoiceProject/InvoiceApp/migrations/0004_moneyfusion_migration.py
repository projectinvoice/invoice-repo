# Generated manually: migration de CinetPay vers MoneyFusion (FusionPay)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('InvoiceApp', '0003_promocode_promocoderedemption'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionpayment',
            name='provider_token',
            field=models.CharField(blank=True, db_index=True, default='', max_length=150, verbose_name='Token MoneyFusion (tokenPay)'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='subscriptionpayment',
            name='transaction_id',
            field=models.CharField(max_length=100, unique=True, verbose_name='ID de transaction interne'),
        ),
        migrations.AlterField(
            model_name='subscriptionpayment',
            name='operator_id',
            field=models.CharField(blank=True, max_length=100, verbose_name='Référence opérateur'),
        ),
    ]
