from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Agent, AgentRole, Engine, Product, Client,
    Supplier, Supply, Sale, Invoice, PaymentType, PaymentMethod
)

class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('username', 'company_name', 'company_email', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Informations entreprise', {'fields': ('company_name', 'company_email', 'phone', 'address', 'logo')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates importantes', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'company_name', 'company_email', 'phone', 'address', 'logo', 'password1', 'password2', 'is_active', 'is_staff')
        }),
    )
    search_fields = ('username', 'company_name', 'company_email')
    ordering = ('username',)

# Enregistrement des modèles
admin.site.register(User, CustomUserAdmin)
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
