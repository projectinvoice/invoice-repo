# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Agent, AgentRole, Engine, Product, Client, 
    Supplier, Supply, Sale, Invoice, PaymentType, PaymentMethod
)

# Enregistrement des modèles
admin.site.register(User, UserAdmin)
admin.site.register(AgentRole)
admin.site.register(Agent)
admin.site.register(Engine)
admin.site.register(Product)
admin.site.register(Client)
admin.site.register(Supplier)
admin.site.register(Supply)
admin.site.register(Sale)
admin.site.register(Invoice)
admin.site.register(PaymentType)
admin.site.register(PaymentMethod)
