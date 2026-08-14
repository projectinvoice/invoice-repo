# Generated manually for the promo code system (accès offert avant abonnement)

import django.db.models.deletion
import InvoiceApp.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('InvoiceApp', '0002_subscription_subscriptionpayment'),
    ]

    operations = [
        migrations.CreateModel(
            name='PromoCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(default=InvoiceApp.models.generate_promo_code, max_length=32, unique=True, verbose_name='Code')),
                ('duration_days', models.PositiveIntegerField(verbose_name='Durée offerte (jours)')),
                ('note', models.CharField(blank=True, max_length=255, verbose_name='Note / campagne (ex: Lancement bêta)')),
                ('max_redemptions', models.PositiveIntegerField(blank=True, null=True, verbose_name="Nombre d'utilisations max (vide = illimité)")),
                ('is_active', models.BooleanField(default=True, verbose_name='Actif')),
                ('valid_until', models.DateTimeField(blank=True, null=True, verbose_name="Date limite d'utilisation (vide = jamais)")),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
            ],
            options={
                'verbose_name': 'Code promo',
                'verbose_name_plural': 'Codes promo',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PromoCodeRedemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('redeemed_at', models.DateTimeField(auto_now_add=True, verbose_name='Utilisé le')),
                ('expires_at', models.DateTimeField(verbose_name='Accès offert jusqu\'au')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='promo_redemptions', to=settings.AUTH_USER_MODEL, verbose_name='Entreprise')),
                ('promo_code', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='redemptions', to='InvoiceApp.promocode', verbose_name='Code promo')),
            ],
            options={
                'verbose_name': 'Utilisation de code promo',
                'verbose_name_plural': 'Utilisations de codes promo',
                'ordering': ['-redeemed_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='promocoderedemption',
            constraint=models.UniqueConstraint(fields=('promo_code', 'company'), name='unique_promo_redemption_per_company'),
        ),
    ]
