import json
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Client, Product, Sale, SaleItem


class SaleMultiItemTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username='salesuser', password='123456', company_name='Sales Company')
        self.client.force_login(self.user)
        self.client_obj = Client.objects.create(company=self.user, name='Client Test')
        self.product_one = Product.objects.create(company=self.user, name='Produit A', price='10.50', stock_quantity=5)
        self.product_two = Product.objects.create(company=self.user, name='Produit B', price='25.00', stock_quantity=3)

    def test_creates_sale_with_multiple_items(self):
        response = self.client.post(reverse('add_sale'), {
            'client_id': self.client_obj.id,
            'currency': 'EUR',
            'sale_items': json.dumps([
                {'product_id': self.product_one.id, 'quantity': 2, 'unit_price': '10.50'},
                {'product_id': self.product_two.id, 'quantity': 1, 'unit_price': '25.00'},
            ]),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        sale = Sale.objects.get(id=payload['sale_id'])
        self.assertEqual(sale.sale_items.count(), 2)
        self.assertEqual(sale.total_price, Decimal('46.00'))
        self.assertEqual(sale.currency, 'EUR')

    def test_sales_page_renders_edit_payload_for_existing_sale(self):
        sale = Sale.objects.create(company=self.user, client=self.client_obj, currency='EUR')
        SaleItem.objects.create(sale=sale, product=self.product_one, quantity=2, unit_price='10.50', currency='EUR')

        response = self.client.get(reverse('list_sales'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn("data-items='", content)
        self.assertIn(str(sale.id), content)

    def test_creates_sale_without_explicit_unit_price_uses_product_price(self):
        response = self.client.post(reverse('add_sale'), {
            'client_id': self.client_obj.id,
            'currency': 'EUR',
            'sale_items': json.dumps([
                {'product_id': self.product_one.id, 'quantity': 2},
            ]),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        sale = Sale.objects.get(id=payload['sale_id'])
        item = sale.sale_items.get(product=self.product_one)
        self.assertEqual(item.unit_price, Decimal('10.50'))
        self.assertEqual(item.total_price, Decimal('21.00'))

    def test_creates_sale_deducts_stock_quantity(self):
        response = self.client.post(reverse('add_sale'), {
            'client_id': self.client_obj.id,
            'currency': 'EUR',
            'sale_items': json.dumps([
                {'product_id': self.product_one.id, 'quantity': 2, 'unit_price': '10.50'},
            ]),
        })

        self.assertEqual(response.status_code, 200)
        self.product_one.refresh_from_db()
        self.assertEqual(self.product_one.stock_quantity, 3)

    def test_edits_sale_recalculates_stock_from_previous_quantity(self):
        sale = Sale.objects.create(company=self.user, client=self.client_obj, currency='EUR')
        SaleItem.objects.create(sale=sale, product=self.product_one, quantity=6, unit_price='10.50', currency='EUR')
        # Stock initial de 50 moins les 6 unités de la vente initiale = 44 restants en stock
        self.product_one.stock_quantity = 44
        self.product_one.save(update_fields=['stock_quantity'])

        response = self.client.post(reverse('add_sale'), {
            'sale_id': sale.id,
            'client_id': self.client_obj.id,
            'currency': 'EUR',
            'sale_items': json.dumps([
                {'product_id': self.product_one.id, 'quantity': 7, 'unit_price': '10.50'},
            ]),
        })

        self.assertEqual(response.status_code, 200)
        self.product_one.refresh_from_db()
        self.assertEqual(self.product_one.stock_quantity, 43)


class SubscriptionReactivationAndStockTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        from .models import Subscription, PromoCode, Agent, Engine, AgentStock, StockReturn, StockReturnItem
        self.timezone = timezone
        self.Subscription = Subscription
        self.PromoCode = PromoCode
        self.Agent = Agent
        self.Engine = Engine
        self.AgentStock = AgentStock
        self.StockReturn = StockReturn
        self.StockReturnItem = StockReturnItem
        self.User = get_user_model()
        self.company = self.User.objects.create_user(
            username='sub@company.com',
            email='sub@company.com',
            password='StrongPassword123!',
            company_name='Sub Company',
            is_active=False,
        )
        self.sub = Subscription.objects.create(
            company=self.company,
            plan='monthly',
            trial_end_date=timezone.now() - timezone.timedelta(days=10),
        )

    def test_extend_after_payment_reactivates_inactive_company_and_unblocks_subscription(self):
        self.assertTrue(self.sub.is_blocked)
        self.assertFalse(self.company.is_active)

        self.sub.extend_after_payment()
        self.company.refresh_from_db()
        self.sub.refresh_from_db()

        self.assertTrue(self.company.is_active)
        self.assertFalse(self.sub.is_blocked)
        self.assertEqual(self.sub.status, 'active')

    def test_redeem_promo_code_reactivates_inactive_company_and_unblocks_subscription(self):
        from .models import redeem_promo_code
        promo = self.PromoCode.objects.create(code='REACTIVATE30', duration_days=30, is_active=True)
        self.assertTrue(self.sub.is_blocked)
        self.assertFalse(self.company.is_active)

        success, _ = redeem_promo_code(self.company, 'REACTIVATE30')
        self.company.refresh_from_db()
        self.sub.refresh_from_db()

        self.assertTrue(success)
        self.assertTrue(self.company.is_active)
        self.assertFalse(self.sub.is_blocked)
        self.assertEqual(self.sub.status, 'promo')

    def test_stock_load_saves_engine_and_stock_return_edit_restores_preview(self):
        self.company.is_active = True
        self.company.save(update_fields=['is_active'])
        self.sub.extend_after_payment()
        self.client.force_login(self.company)

        engine = self.Engine.objects.create(company=self.company, name='Tricycle 01')
        agent = self.Agent.objects.create(company=self.company, name='Vendeur Test', engine=engine)
        product = Product.objects.create(company=self.company, name='Sac Riz', price='15000', stock_quantity=20)

        res_load = self.client.post(reverse('add_stock_load'), {
            'agent_id': agent.id,
            'engine_id': engine.id,
            'note': 'Tournee Nord',
            'items': json.dumps([{'product_id': product.id, 'quantity': 10, 'unit_price': '15000'}]),
        })
        self.assertEqual(res_load.status_code, 200)
        self.assertTrue(res_load.json()['success'])

        # Retour initial de 8 unités (il reste 2 au vendeur)
        res_ret = self.client.post(reverse('add_stock_return'), {
            'agent_id': agent.id,
            'note': 'Retour soir',
            'items': json.dumps([{'product_id': product.id, 'quantity': 8}]),
        })
        self.assertEqual(res_ret.status_code, 200)
        return_id = res_ret.json()['return_id']

        # Modification du retour de 8 à 9 unités (doit réussir car 2 en stock vendeur + 8 ancien retour = 10 >= 9)
        res_edit = self.client.post(reverse('add_stock_return'), {
            'return_id': return_id,
            'agent_id': agent.id,
            'note': 'Retour corrige',
            'items': json.dumps([{'product_id': product.id, 'quantity': 9}]),
        })
        self.assertEqual(res_edit.status_code, 200)
        self.assertTrue(res_edit.json()['success'])