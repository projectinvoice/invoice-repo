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
        self.product_one.stock_quantity = 50
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