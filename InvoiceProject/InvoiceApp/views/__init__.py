"""
Package de vues InvoiceApp, decoupe par domaine metier (voir _common.py pour les
imports partages). Ce fichier ré-exporte tout pour que le code existant qui fait
`from InvoiceApp import views as invoice_views` puis `invoice_views.dashboard(...)`
continue de fonctionner sans aucune modification.
"""

from .ai_assistant import GEMINI_API_URL_TEMPLATE, CURRENCY_SYMBOLS, _ai_parse_date, _ai_money, _ai_tool_get_ventes, _ai_tool_get_etat_financier, _ai_tool_get_produits_stock, _ai_tool_get_clients, _ai_tool_get_factures, AI_TOOL_FUNCTIONS, AI_FUNCTION_DECLARATIONS, AI_SYSTEM_PROMPT, _ai_run_tool, ai_chat_init, ai_chat_api
from .auth import landing, _send_activation_email, register_company, login_view, forgot_password, reset_password_confirm, activate_account, resend_activation_email, change_password, delete_account, logout_view
from .subscription import _moneyfusion_configured, subscription_page, apply_promo_code, promo_codes_admin, create_promo_code, toggle_promo_code, initiate_subscription_payment, _verify_and_apply_payment, moneyfusion_webhook, moneyfusion_return
from .dashboard import MONTH_LABELS_FR, _monthly_revenue, _sales_breakdown_by_product, _revenue_by_period, _top_products, _agents_performance, dashboard, api_dashboard_ca
from .company import company_settings
from .agents import manage_agent_roles, list_agents, list_engines, add_agent_role, delete_agent_role, add_agent, delete_agent, add_engine, delete_engine
from .products import list_products, add_product, delete_product
from .clients import list_clients, add_client, delete_client
from .suppliers import list_suppliers, list_supplies, add_supplier, delete_supplier, add_supply, delete_supply
from .sales import list_sales, add_sale, delete_sale
from .invoices import list_invoices, add_invoice, delete_invoice, record_invoice_payment, _build_invoice_pdf_bytes, _render_invoice_pdf, invoice_pdf
from .vendor import generate_invoice_number, agent_login_required, vendor_login, vendor_logout, vendor_invoice_pdf, vendor_dashboard, vendor_add_sale, vendor_add_payment
from .stock import list_stock_loads, add_stock_load, delete_stock_load, add_stock_return, delete_stock_return