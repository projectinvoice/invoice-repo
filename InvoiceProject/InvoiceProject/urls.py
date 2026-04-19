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
    path('admin/', admin.site.urls),
    path('register/', invoice_views.register_company, name='register'),
    path('login/', invoice_views.login_view, name='login'),
    path('dashboard/', invoice_views.dashboard, name='dashboard'),
    path('change-password/', invoice_views.change_password, name='change_password'),
    path('delete-account/', invoice_views.delete_account, name='delete_account'),
    path('stock/', invoice_views.stock, name='stock'),
    path('seller/', invoice_views.seller, name='seller'),
    path('suppliers/', invoice_views.supplier_list, name='supplier_list'),

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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
