from django.db import models
from django.contrib.auth.models import AbstractUser

# Modèle utilisateur personnalisé (l'entreprise elle-même est l'utilisateur)
class User(AbstractUser):
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True, verbose_name="Logo de l'entreprise")
    # Champs supplémentaires pour l'entreprise
    company_name = models.CharField(max_length=255, verbose_name="Nom de l'entreprise")
    company_email = models.EmailField(verbose_name="Adresse email")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    address = models.TextField(blank=True, verbose_name="Adresse")
    add_date = models.DateTimeField(auto_now_add=True, verbose_name="Date d'inscription")

    def __str__(self):
        return self.company_name

    class Meta:
        verbose_name = "Entreprise"
        verbose_name_plural = "Entreprises"

# Modèle pour les rôles d'agent
class AgentRole(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_roles', verbose_name="Entreprise")
    name = models.CharField(max_length=100, verbose_name="Nom du rôle")
    description = models.TextField(blank=True, verbose_name="Description")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Rôle d'agent"
        verbose_name_plural = "Rôles d'agents"
        unique_together = ('company', 'name')

# Modèle pour les agents (sous-utilisateurs ajoutés par l'entreprise, sans authentification)
class Agent(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agents', verbose_name="Entreprise")
    name = models.CharField(max_length=255, verbose_name="Nom")
    email = models.EmailField(blank=True, verbose_name="Email")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    role = models.ForeignKey(AgentRole, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Rôle")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

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
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products', verbose_name="Entreprise")
    image = models.ImageField(upload_to="product_images/", blank=True, null=True, verbose_name="Image du produit")
    name = models.CharField(max_length=255, verbose_name="Nom du produit")
    description = models.TextField(blank=True, verbose_name="Description")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix")
    stock_quantity = models.PositiveIntegerField(default=0, verbose_name="Quantité en stock")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def __str__(self):
        return f"{self.name} ({self.company.company_name})"

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"

# Modèle pour les clients
class Client(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clients', verbose_name="Entreprise")
    name = models.CharField(max_length=255, verbose_name="Nom du client")
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
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_types', verbose_name="Entreprise")
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
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date")

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Approvisionnement de {self.product.name} ({self.company.company_name})"

    class Meta:
        verbose_name = "Approvisionnement"
        verbose_name_plural = "Approvisionnements"

# Modèle pour les ventes
class Sale(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sales', verbose_name="Entreprise")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='sales', verbose_name="Client")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sales', verbose_name="Produit")
    quantity = models.PositiveIntegerField(verbose_name="Quantité")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix unitaire")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix total")
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date")

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Vente de {self.product.name} à {self.client.name} ({self.company.company_name})"

    class Meta:
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"

# Modèle pour les factures
class Invoice(models.Model):
    company = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invoices', verbose_name="Entreprise")
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name='invoice', verbose_name="Vente associée")
    invoice_number = models.CharField(max_length=50, unique=True, verbose_name="Numéro de facture")
    issued_date = models.DateTimeField(auto_now_add=True, verbose_name="Date d'émission")
    due_date = models.DateField(verbose_name="Date d'échéance")
    status = models.CharField(max_length=20, choices=[
        ('pending', 'En attente'),
        ('paid', 'Payée'),
        ('overdue', 'En retard')
    ], default='pending', verbose_name="Statut")

    def __str__(self):
        return f"Facture {self.invoice_number} ({self.company.company_name})"

    class Meta:
        verbose_name = "Facture"
        verbose_name_plural = "Factures"