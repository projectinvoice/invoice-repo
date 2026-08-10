from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('InvoiceApp', '0002_supply_multiline'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='default_currency',
            field=models.CharField(
                choices=[('EUR', 'Euro (€)'), ('USD', 'Dollar US ($)'), ('XOF', 'Franc CFA (FCFA)')],
                default='EUR',
                max_length=3,
                verbose_name="Devise de l'entreprise",
            ),
        ),
    ]