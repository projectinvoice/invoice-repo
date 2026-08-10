import json
import random
import string
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password, check_password

# Modèle utilisateur personnalisé (l'entreprise elle-même est l'utilisateur)
class User(AbstractUser):
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True, verbose_name="Logo de l'entreprise")
    # Champs supplémentaires pour l'entreprise
    company_name = models.CharField(max_length=255, verbose_name="Nom de l'entreprise")
    company_email = models.EmailField(blank=True, null=True,verbose_name="Adresse email")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    address = models.TextField(blank=True, verbose_name="Adresse")
    add_date = models.DateTimeField(auto_now_add=True, verbose_name="Date d'inscription",blank=True, null=True,)

    # Code que l'entreprise communique à ses vendeurs pour se connecter à leur espace dédié
    agent_login_code = models.CharField(max_length=8, unique=True, blank=True, verbose_name="Code de connexion vendeurs")
    # Compteur utilisé pour générer les numéros de facture de façon séquentielle et sans collision
    next_invoice_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro de facture")

    def save(self, *args, **kwargs):
        if not self.agent_login_code:
            self.agent_login_code = self._generate_unique_login_code()
        super().save(*args, **kwargs)

    def _generate_unique_login_code(self):
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(random.choices(alphabet, k=6))
            if not User.objects.filter(agent_login_code=code).exists():
                return code

    def __str__(self):
        return self.company_name

    class Meta:
        verbose_name = "Entreprise"
        verbose_name_plural = "Entreprises"

# Modèle pour les rôles d'agent
class AgentRole(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_roles', verbose_name="Entreprise", default=1)
    name = models.CharField(max_length=100, verbose_name="Nom du rôle")
    description = models.TextField(blank=True, verbose_name="Description")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Rôle d'agent"
        verbose_name_plural = "Rôles d'agents"
        unique_together = ('company', 'name')

# Modèle pour les agents (sous-utilisateurs ajoutés par l'entreprise)
class Agent(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agents', verbose_name="Entreprise")
    name = models.CharField(max_length=255, verbose_name="Nom")
    email = models.EmailField(blank=True, verbose_name="Email")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    role = models.ForeignKey(AgentRole, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Rôle")
    engine = models.ForeignKey('Engine', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_agents', verbose_name="Engin attribué")
    pin_hash = models.CharField(max_length=128, blank=True, verbose_name="PIN (haché)")
    is_active = models.BooleanField(default=True, verbose_name="Accès actif")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def set_pin(self, raw_pin):
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin):
        if not self.pin_hash:
            return False
        return check_password(raw_pin, self.pin_hash)

    def __str__(self):
        return f"{self.name} ({self.company.company_name})"

    class Meta:
        verbose_name = "Agent"
        verbose_name_plural = "Agents"

# Modèle pour les engins/équipements
class Engine(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='engines', verbose_name="Entreprise")
    name = models.CharField(max_length=255, verbose_name="Nom de l'engin")
    description = models.TextField(blank=True, verbose_name="Description")
    serial_number = models.CharField(max_length=100, blank=True, verbose_name="Numéro de série")
    status = models.CharField(max_length=50, choices=[
        ('active', 'Actif'),
        ('inactive', 'Inactif'),
        ('maintenance', 'En maintenance')
    ], default='active', verbose_name="Statut")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def __str__(self):
        return f"{self.name} ({self.company.company_name})"

    class Meta:
        verbose_name = "Engin"
        verbose_name_plural = "Engins"

# Modèle pour les produits
class Product(models.Model):
    CURRENCY_CHOICES = [
        ('EUR', 'Euro (€)'),
        ('USD', 'Dollar US ($)'),
        ('XOF', 'Franc CFA (FCFA)'),
    ]

    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products', verbose_name="Entreprise")
    image = models.ImageField(upload_to="product_images/", blank=True, null=True, verbose_name="Image du produit")
    name = models.CharField(max_length=255, verbose_name="Nom du produit")
    description = models.TextField(blank=True, verbose_name="Description")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix")
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='EUR', verbose_name="Devise")
    stock_quantity = models.PositiveIntegerField(default=0, verbose_name="Quantité en stock")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def __str__(self):
        return f"{self.name} ({self.company.company_name})"

    @property
    def formatted_price(self):
        """Retourne le prix formaté avec le bon symbole selon la devise."""
        symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
        symbol = symbols.get(self.currency, self.currency)
        if self.currency == 'XOF':
            amount = f"{self.price:,.0f}".replace(',', ' ')
        else:
            amount = f"{self.price:,.2f}".replace(',', ' ')
        return f"{symbol}{amount}" if self.currency == 'USD' else f"{amount} {symbol}"

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"

# Modèle pour les clients
class Client(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clients', verbose_name="Entreprise")
    name = models.CharField(max_length=255, verbose_name="Nom du client")
    shop_name = models.CharField(max_length=255, blank=True, verbose_name="Nom du magasin")
    email = models.EmailField(blank=True, verbose_name="Email")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    address = models.TextField(blank=True, verbose_name="Adresse")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def __str__(self):
        return f"{self.name} ({self.company.company_name})"

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"

# Modèle pour les types de paiement
class PaymentType(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_types', verbose_name="Entreprise", default=1)
    name = models.CharField(max_length=100, verbose_name="Nom du type de paiement")
    description = models.TextField(blank=True, verbose_name="Description")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Type de paiement"
        verbose_name_plural = "Types de paiement"
        unique_together = ('company', 'name')

# Modèle pour les modes de paiement
class PaymentMethod(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_methods', verbose_name="Entreprise")
    name = models.CharField(max_length=100, verbose_name="Nom du mode de paiement")
    payment_type = models.ForeignKey(PaymentType, on_delete=models.SET_NULL, null=True, verbose_name="Type de paiement")
    description = models.TextField(blank=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def __str__(self):
        return f"{self.name} ({self.company.company_name})"

    class Meta:
        verbose_name = "Mode de paiement"
        verbose_name_plural = "Modes de paiement"

# Modèle pour les fournisseurs
class Supplier(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='suppliers', verbose_name="Entreprise")
    name = models.CharField(max_length=255, verbose_name="Nom du fournisseur")
    email = models.EmailField(blank=True, verbose_name="Email")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    address = models.TextField(blank=True, verbose_name="Adresse")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def __str__(self):
        return f"{self.name} ({self.company.company_name})"

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"

# Modèle pour les approvisionnements (achats de stock)
class Supply(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='supplies', verbose_name="Entreprise")
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='supplies', verbose_name="Fournisseur")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='supplies', verbose_name="Produit")
    quantity = models.PositiveIntegerField(verbose_name="Quantité")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix unitaire")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix total")
    currency = models.CharField(max_length=3, choices=Product.CURRENCY_CHOICES, default='EUR', verbose_name="Devise")
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date")

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Approvisionnement de {self.product.name} ({self.company.company_name})"

    @property
    def formatted_total_price(self):
        symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
        symbol = symbols.get(self.currency, self.currency)
        amount = f"{self.total_price:,.0f}".replace(',', ' ') if self.currency == 'XOF' else f"{self.total_price:,.2f}".replace(',', ' ')
        return f"{symbol}{amount}" if self.currency == 'USD' else f"{amount} {symbol}"

    class Meta:
        verbose_name = "Approvisionnement"
        verbose_name_plural = "Approvisionnements"

# Modèle pour les ventes
class Sale(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sales', verbose_name="Entreprise")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='sales', verbose_name="Client")
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales', verbose_name="Agent")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sales', verbose_name="Produit", null=True, blank=True)
    quantity = models.PositiveIntegerField(default=0, verbose_name="Quantité")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Prix unitaire")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Prix total")
    currency = models.CharField(max_length=3, choices=Product.CURRENCY_CHOICES, default='EUR', verbose_name="Devise")
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date")

    def save(self, *args, **kwargs):
        if self.pk and self.sale_items.exists():
            self.total_price = sum((item.total_price for item in self.sale_items.all()), Decimal('0.00'))
            first_item = self.sale_items.order_by('id').first()
            self.product = first_item.product
            self.quantity = sum((item.quantity for item in self.sale_items.all()), 0)
            self.unit_price = first_item.unit_price
            self.currency = first_item.currency
        elif self.total_price == Decimal('0.00'):
            self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Vente de {self.item_names or 'plusieurs produits'} à {self.client.name} ({self.company.company_name})"

    @property
    def item_names(self):
        names = [item.product.name for item in self.sale_items.all() if item.product]
        return ', '.join(names)

    @property
    def serialized_items(self):
        items = [
            {
                'product_id': item.product_id,
                'quantity': item.quantity,
                'unit_price': str(item.unit_price),
            }
            for item in self.sale_items.all()
        ]
        return json.dumps(items)

    @property
    def formatted_total_price(self):
        symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
        symbol = symbols.get(self.currency, self.currency)
        amount = f"{self.total_price:,.0f}".replace(',', ' ') if self.currency == 'XOF' else f"{self.total_price:,.2f}".replace(',', ' ')
        return f"{symbol}{amount}" if self.currency == 'USD' else f"{amount} {symbol}"

    class Meta:
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='sale_items', verbose_name="Vente")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sale_items', verbose_name="Produit")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantité")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Prix unitaire")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Prix total")
    currency = models.CharField(max_length=3, choices=Product.CURRENCY_CHOICES, default='EUR', verbose_name="Devise")

    def save(self, *args, **kwargs):
        quantity = int(self.quantity)
        unit_price = Decimal(str(self.unit_price))
        self.total_price = Decimal(quantity) * unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    class Meta:
        verbose_name = "Ligne de vente"
        verbose_name_plural = "Lignes de vente"

# Modèle pour les factures
class Invoice(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invoices', verbose_name="Entreprise")
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name='invoice', verbose_name="Vente associée")
    invoice_number = models.CharField(max_length=50, verbose_name="Numéro de facture")
    issued_date = models.DateTimeField(auto_now_add=True, verbose_name="Date d'émission")
    due_date = models.DateField(verbose_name="Date d'échéance")
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Montant déjà payé")
    status = models.CharField(max_length=20, choices=[
        ('pending', 'En attente (crédit)'),
        ('partial', 'Paiement partiel'),
        ('paid', 'Payée'),
        ('overdue', 'En retard')
    ], default='pending', verbose_name="Statut")

    def __str__(self):
        return f"Facture {self.invoice_number} ({self.company.company_name})"

    @property
    def balance_due(self):
        """Ce qu'il reste à payer."""
        total = self.sale.total_price if self.sale else Decimal('0.00')
        remaining = total - self.amount_paid
        return remaining if remaining > 0 else Decimal('0.00')

    @property
    def formatted_amount_paid(self):
        return self._format_money(self.amount_paid)

    @property
    def formatted_balance_due(self):
        return self._format_money(self.balance_due)

    def _format_money(self, value):
        currency = self.sale.currency if self.sale else 'EUR'
        symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
        symbol = symbols.get(currency, currency)
        amount = f"{value:,.0f}".replace(',', ' ') if currency == 'XOF' else f"{value:,.2f}".replace(',', ' ')
        return f"{symbol}{amount}" if currency == 'USD' else f"{amount} {symbol}"

    def refresh_status(self):
        """Recalcule le statut à partir du montant payé. À appeler après chaque paiement enregistré."""
        total = self.sale.total_price if self.sale else Decimal('0.00')
        if self.amount_paid <= 0:
            self.status = 'overdue' if self.due_date < timezone.now().date() else 'pending'
        elif self.amount_paid < total:
            self.status = 'partial'
        else:
            self.status = 'paid'

    class Meta:
        verbose_name = "Facture"
        verbose_name_plural = "Factures"
        unique_together = ('company', 'invoice_number')


# Historique des versements d'une facture (comptant, avance, ou remboursement de crédit)
class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments', verbose_name="Facture")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Montant versé")
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date du versement")
    note = models.CharField(max_length=255, blank=True, verbose_name="Note")
    recorded_by_agent = models.ForeignKey(
        Agent, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_payments', verbose_name="Enregistré par (vendeur)"
    )

    def __str__(self):
        return f"Versement {self.amount} — Facture {self.invoice.invoice_number}"

    @property
    def formatted_amount(self):
        currency = self.invoice.sale.currency if self.invoice.sale else 'EUR'
        symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
        symbol = symbols.get(currency, currency)
        amount = f"{self.amount:,.0f}".replace(',', ' ') if currency == 'XOF' else f"{self.amount:,.2f}".replace(',', ' ')
        return f"{symbol}{amount}" if currency == 'USD' else f"{amount} {symbol}"

    class Meta:
        verbose_name = "Versement"
        verbose_name_plural = "Versements"
        ordering = ['date']


# ═══════════════════════════════════════════════════════════════
# Stock personnel des vendeurs (chargement / retour de tournée)
# ═══════════════════════════════════════════════════════════════

# Le stock que chaque vendeur transporte réellement (différent du stock magasin)
class AgentStock(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='stocks', verbose_name="Agent")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='agent_stocks', verbose_name="Produit")
    quantity = models.PositiveIntegerField(default=0, verbose_name="Quantité chez le vendeur")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Prix de vente fixé")
    currency = models.CharField(max_length=3, choices=Product.CURRENCY_CHOICES, default='EUR', verbose_name="Devise")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Dernière mise à jour")

    def __str__(self):
        return f"{self.agent.name} — {self.product.name} ({self.quantity})"

    @property
    def formatted_unit_price(self):
        symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
        symbol = symbols.get(self.currency, self.currency)
        amount = f"{self.unit_price:,.0f}".replace(',', ' ') if self.currency == 'XOF' else f"{self.unit_price:,.2f}".replace(',', ' ')
        return f"{symbol}{amount}" if self.currency == 'USD' else f"{amount} {symbol}"

    class Meta:
        verbose_name = "Stock vendeur"
        verbose_name_plural = "Stocks vendeurs"
        unique_together = ('agent', 'product')


# La "fiche" de chargement : ce que la secrétaire a fait sortir du magasin pour un vendeur
class StockLoad(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stock_loads', verbose_name="Entreprise")
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='stock_loads', verbose_name="Agent")
    engine = models.ForeignKey(Engine, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_loads', verbose_name="Engin utilisé pour cette tournée")
    note = models.CharField(max_length=255, blank=True, verbose_name="Note (ex: destination, tournée)")
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date de chargement")

    def __str__(self):
        return f"Chargement {self.agent.name} du {self.date.strftime('%d/%m/%Y')}"

    class Meta:
        verbose_name = "Chargement"
        verbose_name_plural = "Chargements"
        ordering = ['-date']


class StockLoadItem(models.Model):
    load = models.ForeignKey(StockLoad, on_delete=models.CASCADE, related_name='items', verbose_name="Chargement")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_load_items', verbose_name="Produit")
    quantity = models.PositiveIntegerField(verbose_name="Quantité chargée")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix fixé pour le vendeur")
    currency = models.CharField(max_length=3, choices=Product.CURRENCY_CHOICES, default='EUR', verbose_name="Devise")

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    class Meta:
        verbose_name = "Ligne de chargement"
        verbose_name_plural = "Lignes de chargement"


# Le retour de marchandise invendue vers le magasin
class StockReturn(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stock_returns', verbose_name="Entreprise")
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='stock_returns', verbose_name="Agent")
    note = models.CharField(max_length=255, blank=True, verbose_name="Note")
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date de retour")

    def __str__(self):
        return f"Retour {self.agent.name} du {self.date.strftime('%d/%m/%Y')}"

    class Meta:
        verbose_name = "Retour de stock"
        verbose_name_plural = "Retours de stock"
        ordering = ['-date']


class StockReturnItem(models.Model):
    stock_return = models.ForeignKey(StockReturn, on_delete=models.CASCADE, related_name='items', verbose_name="Retour")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_return_items', verbose_name="Produit")
    quantity = models.PositiveIntegerField(verbose_name="Quantité retournée")

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    class Meta:
        verbose_name = "Ligne de retour"
        verbose_name_plural = "Lignes de retour"