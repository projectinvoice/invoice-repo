"""
URL configuration for InvoiceProject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from InvoiceApp import views as invoice_views

urlpatterns = [
    path('', invoice_views.landing, name='landing'),
    path('admin/', admin.site.urls),
    path('register/', invoice_views.register_company, name='register'),
    path('login/', invoice_views.login_view, name='login'),
    path('mot-de-passe-oublie/', invoice_views.forgot_password, name='forgot_password'),
    path('reinitialiser-mot-de-passe/<uidb64>/<token>/', invoice_views.reset_password_confirm, name='reset_password_confirm'),
    path('logout/', invoice_views.logout_view, name='logout'),
    path('dashboard/', invoice_views.dashboard, name='dashboard'),
    path('api/dashboard/ca/', invoice_views.api_dashboard_ca, name='api_dashboard_ca'),
    path('company-settings/', invoice_views.company_settings, name='company_settings'),
    path('manage-agent-roles/', invoice_views.manage_agent_roles, name='manage_agent_roles'),

    # Abonnement & paiement MoneyFusion
    path('subscription/', invoice_views.subscription_page, name='subscription'),
    path('subscription/pay/', invoice_views.initiate_subscription_payment, name='initiate_subscription_payment'),
    path('subscription/webhook/', invoice_views.moneyfusion_webhook, name='moneyfusion_webhook'),
    path('subscription/return/', invoice_views.moneyfusion_return, name='moneyfusion_return'),
    path('subscription/promo-code/', invoice_views.apply_promo_code, name='apply_promo_code'),

    # Gestion des codes promo (réservé au staff)
    path('admin-tools/promo-codes/', invoice_views.promo_codes_admin, name='promo_codes_admin'),
    path('admin-tools/promo-codes/create/', invoice_views.create_promo_code, name='create_promo_code'),
    path('admin-tools/promo-codes/<int:promo_id>/toggle/', invoice_views.toggle_promo_code, name='toggle_promo_code'),
    
    # List views for all entities
    path('list-agents/', invoice_views.list_agents, name='list_agents'),
    path('list-engines/', invoice_views.list_engines, name='list_engines'),
    path('list-products/', invoice_views.list_products, name='list_products'),
    path('list-clients/', invoice_views.list_clients, name='list_clients'),
    path('list-suppliers/', invoice_views.list_suppliers, name='list_suppliers'),
    path('list-payment-types/', invoice_views.list_payment_types, name='list_payment_types'),
    path('list-payment-methods/', invoice_views.list_payment_methods, name='list_payment_methods'),
    path('list-supplies/', invoice_views.list_supplies, name='list_supplies'),
    path('list-sales/', invoice_views.list_sales, name='list_sales'),
    path('list-invoices/', invoice_views.list_invoices, name='list_invoices'),
    
    path('change-password/', invoice_views.change_password, name='change_password'),
    path('delete-account/', invoice_views.delete_account, name='delete_account'),

    path('add-agent-role/', invoice_views.add_agent_role, name='add_agent_role'),
    path('delete-agent-role/', invoice_views.delete_agent_role, name='delete_agent_role'),
    path('add-agent/', invoice_views.add_agent, name='add_agent'),
    path('delete-agent/', invoice_views.delete_agent, name='delete_agent'),
    path('add-engine/', invoice_views.add_engine, name='add_engine'),
    path('delete-engine/', invoice_views.delete_engine, name='delete_engine'),
    path('add-product/', invoice_views.add_product, name='add_product'),
    path('delete-product/', invoice_views.delete_product, name='delete_product'),
    path('add-client/', invoice_views.add_client, name='add_client'),
    path('delete-client/', invoice_views.delete_client, name='delete_client'),
    path('add-payment-type/', invoice_views.add_payment_type, name='add_payment_type'),
    path('delete-payment-type/', invoice_views.delete_payment_type, name='delete_payment_type'),
    path('add-payment-method/', invoice_views.add_payment_method, name='add_payment_method'),
    path('delete-payment-method/', invoice_views.delete_payment_method, name='delete_payment_method'),
    path('add-supplier/', invoice_views.add_supplier, name='add_supplier'),
    path('delete-supplier/', invoice_views.delete_supplier, name='delete_supplier'),
    path('add-supply/', invoice_views.add_supply, name='add_supply'),
    path('delete-supply/', invoice_views.delete_supply, name='delete_supply'),
    path('add-sale/', invoice_views.add_sale, name='add_sale'),
    path('delete-sale/', invoice_views.delete_sale, name='delete_sale'),
    path('add-invoice/', invoice_views.add_invoice, name='add_invoice'),
    path('delete-invoice/', invoice_views.delete_invoice, name='delete_invoice'),
    path('record-invoice-payment/', invoice_views.record_invoice_payment, name='record_invoice_payment'),
    path('invoices/<int:invoice_id>/pdf/', invoice_views.invoice_pdf, name='invoice_pdf'),

    # Espace vendeur (agents) — authentification séparée par code entreprise + PIN
    path('vendeur/login/', invoice_views.vendor_login, name='vendor_login'),
    path('vendeur/logout/', invoice_views.vendor_logout, name='vendor_logout'),
    path('vendeur/', invoice_views.vendor_dashboard, name='vendor_dashboard'),
    path('vendeur/vente/', invoice_views.vendor_add_sale, name='vendor_add_sale'),
    path('vendeur/factures/<int:invoice_id>/pdf/', invoice_views.vendor_invoice_pdf, name='vendor_invoice_pdf'),
    path('vendeur/paiement/', invoice_views.vendor_add_payment, name='vendor_add_payment'),

    # Stock vendeur (chargement / retour de tournée) — géré par l'admin
    path('stock-loads/', invoice_views.list_stock_loads, name='list_stock_loads'),
    path('add-stock-load/', invoice_views.add_stock_load, name='add_stock_load'),
    path('add-stock-return/', invoice_views.add_stock_return, name='add_stock_return'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)