# Generated manually for the subscription system (essai gratuit + CinetPay)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('InvoiceApp', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan', models.CharField(choices=[('monthly', 'Mensuel'), ('annual', 'Annuel')], max_length=10, verbose_name='Plan choisi')),
                ('trial_end_date', models.DateTimeField(verbose_name="Fin de l'essai gratuit")),
                ('active_until', models.DateTimeField(blank=True, null=True, verbose_name='Accès payant valide jusqu\'au')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date de création')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Dernière mise à jour')),
                ('company', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to=settings.AUTH_USER_MODEL, verbose_name='Entreprise')),
            ],
            options={
                'verbose_name': 'Abonnement',
                'verbose_name_plural': 'Abonnements',
            },
        ),
        migrations.CreateModel(
            name='SubscriptionPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan', models.CharField(choices=[('monthly', 'Mensuel'), ('annual', 'Annuel')], max_length=10, verbose_name='Plan payé')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Montant (FCFA)')),
                ('transaction_id', models.CharField(max_length=100, unique=True, verbose_name='ID de transaction CinetPay')),
                ('status', models.CharField(choices=[('pending', 'En attente'), ('success', 'Réussi'), ('failed', 'Échoué')], default='pending', max_length=10, verbose_name='Statut')),
                ('payment_method', models.CharField(blank=True, max_length=50, verbose_name='Moyen de paiement')),
                ('operator_id', models.CharField(blank=True, max_length=100, verbose_name='Référence opérateur CinetPay')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date de création')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Dernière mise à jour')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscription_payments', to=settings.AUTH_USER_MODEL, verbose_name='Entreprise')),
            ],
            options={
                'verbose_name': "Paiement d'abonnement",
                'verbose_name_plural': "Paiements d'abonnement",
                'ordering': ['-created_at'],
            },
        ),
    ]
