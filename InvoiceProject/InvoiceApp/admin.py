from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Agent, AgentRole, Engine, Product, Client,
    Supplier, Supply, Sale, Invoice,
    Subscription, SubscriptionPayment, PromoCode, PromoCodeRedemption,
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


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('company', 'plan', 'status', 'trial_end_date', 'active_until', 'updated_at')
    list_filter = ('plan',)
    search_fields = ('company__company_name', 'company__email')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description="Statut")
    def status(self, obj):
        return obj.status


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'provider_token', 'company', 'plan', 'amount', 'status', 'payment_method', 'created_at')
    list_filter = ('status', 'plan')
    search_fields = ('transaction_id', 'provider_token', 'company__company_name', 'operator_id')
    readonly_fields = ('created_at', 'updated_at')


class PromoCodeRedemptionInline(admin.TabularInline):
    model = PromoCodeRedemption
    extra = 0
    readonly_fields = ('company', 'redeemed_at', 'expires_at')
    can_delete = False


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'duration_days', 'note', 'redemptions_display', 'is_active', 'valid_until', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'note')
    readonly_fields = ('created_at',)
    inlines = [PromoCodeRedemptionInline]

    @admin.display(description="Utilisations")
    def redemptions_display(self, obj):
        total = obj.redemptions_count
        limit = obj.max_redemptions if obj.max_redemptions is not None else '∞'
        return f"{total} / {limit}"


@admin.register(PromoCodeRedemption)
class PromoCodeRedemptionAdmin(admin.ModelAdmin):
    list_display = ('promo_code', 'company', 'redeemed_at', 'expires_at')
    search_fields = ('promo_code__code', 'company__company_name')
    readonly_fields = ('redeemed_at',)