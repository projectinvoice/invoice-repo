# -*- coding: utf-8 -*-
"""
Tests d'isolation multi-tenant.

Principe de l'app : `request.user` EST l'entreprise. Toute donnée (client, produit,
vente, facture, agent, fournisseur, approvisionnement...) appartient à une entreprise
et ne doit JAMAIS être visible, modifiable ou supprimable par une autre entreprise —
même en devinant un ID (attaque IDOR : Insecure Direct Object Reference).

Ces tests créent systématiquement DEUX entreprises (A et B) avec leurs propres
données, connectent le client de test en tant qu'entreprise A, puis tentent d'agir
sur les objets de l'entreprise B. Le comportement attendu est toujours : soit une
erreur 404/400 explicite, soit un JSON {"success": False}, et dans tous les cas
AUCUNE modification des données de l'entreprise B.

"""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, Client as DjangoTestClient
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import (
    Agent, AgentRole, Client, Engine, Invoice,
    Product, Sale, Supplier, Supply,
)

User = get_user_model()


class MultiTenantFixtureMixin:
    """Prépare deux entreprises isolées (A et B), chacune avec un jeu complet de
    données, plus deux clients de test connectés séparément."""

    def setUp(self):
        self.company_a = User.objects.create_user(
            username='entreprise_a', password='motdepasse123', company_name='Entreprise A',
            default_currency='EUR',
        )
        self.company_b = User.objects.create_user(
            username='entreprise_b', password='motdepasse123', company_name='Entreprise B',
            default_currency='EUR',
        )

        # Un jeu de données complet pour B — c'est CE que A ne doit jamais pouvoir toucher.
        self.client_b = Client.objects.create(company=self.company_b, name='Client de B', shop_name='Boutique B')
        self.product_b = Product.objects.create(company=self.company_b, name='Produit de B', price=Decimal('50.00'), stock_quantity=20)
        self.supplier_b = Supplier.objects.create(company=self.company_b, name='Fournisseur de B')
        self.sale_b = Sale.objects.create(
            company=self.company_b, client=self.client_b, product=self.product_b,
            quantity=2, unit_price=Decimal('50.00'), currency='EUR',
        )
        self.invoice_b = Invoice.objects.create(
            company=self.company_b, sale=self.sale_b, invoice_number='B-0001',
            due_date=date.today() + timedelta(days=30),
        )
        self.supply_b = Supply.objects.create(
            company=self.company_b, supplier=self.supplier_b,
            total_price=Decimal('100.00'), currency='EUR',
        )
        self.role_b = AgentRole.objects.create(company=self.company_b, name='Vendeur B')
        self.engine_b = Engine.objects.create(company=self.company_b, name='Moto B')
        self.agent_b = Agent.objects.create(company=self.company_b, name='Agent de B', role=self.role_b)

        # Quelques données pour A aussi, pour vérifier que les listes de A restent
        # correctes ET ne fuitent pas celles de B.
        self.client_a = Client.objects.create(company=self.company_a, name='Client de A')
        self.product_a = Product.objects.create(company=self.company_a, name='Produit de A', price=Decimal('10.00'), stock_quantity=5)

        # Le client de test HTTP, connecté en tant qu'entreprise A — c'est
        # celui-ci qui va tenter d'accéder aux objets de B.
        self.http = DjangoTestClient()
        self.http.force_login(self.company_a)


class WriteEndpointIsolationTests(MultiTenantFixtureMixin, TestCase):
    """Chaque endpoint d'écriture (add_*/delete_*) doit ignorer/rejeter les IDs
    appartenant à une autre entreprise plutôt que d'agir dessus."""

    def test_cannot_edit_another_companys_client(self):
        resp = self.http.post(reverse('add_client'), {
            'client_id': self.client_b.id,
            'name': 'Nom modifié par A',
        })
        self.assertEqual(resp.json()['success'], False)
        self.client_b.refresh_from_db()
        self.assertEqual(self.client_b.name, 'Client de B')  # inchangé

    def test_cannot_delete_another_companys_client(self):
        resp = self.http.post(reverse('delete_client'), {'client_id': self.client_b.id})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Client.objects.filter(id=self.client_b.id).exists())  # toujours là

    def test_cannot_edit_another_companys_product(self):
        resp = self.http.post(reverse('add_product'), {
            'product_id': self.product_b.id,
            'name': 'Produit piraté',
            'price': '1.00',
        })
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()['success'], False)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.name, 'Produit de B')
        self.assertEqual(self.product_b.price, Decimal('50.00'))

    def test_cannot_delete_another_companys_product(self):
        self.http.post(reverse('delete_product'), {'product_id': self.product_b.id})
        self.assertTrue(Product.objects.filter(id=self.product_b.id).exists())

    def test_cannot_edit_another_companys_sale(self):
        resp = self.http.post(reverse('add_sale'), {
            'sale_id': self.sale_b.id,
            'client_id': self.client_a.id,
            'currency': 'EUR',
            'sale_items': json.dumps([
                {'product_id': self.product_a.id, 'quantity': 1, 'unit_price': '10.00'},
            ]),
        })
        self.assertEqual(resp.status_code, 404)
        self.sale_b.refresh_from_db()
        self.assertEqual(self.sale_b.client_id, self.client_b.id)  # inchangé

    def test_cannot_delete_another_companys_sale(self):
        self.http.post(reverse('delete_sale'), {'sale_id': self.sale_b.id})
        self.assertTrue(Sale.objects.filter(id=self.sale_b.id).exists())

    def test_cannot_create_invoice_for_another_companys_sale(self):
        resp = self.http.post(reverse('add_invoice'), {
            'sale_id': self.sale_b.id,
            'invoice_number': 'VOL-0001',
            'due_date': (date.today() + timedelta(days=10)).isoformat(),
        })
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Invoice.objects.filter(invoice_number='VOL-0001').exists())

    def test_cannot_edit_another_companys_invoice(self):
        resp = self.http.post(reverse('add_invoice'), {
            'invoice_id': self.invoice_b.id,
            'sale_id': self.sale_b.id,
            'invoice_number': 'MODIFIE',
            'due_date': (date.today() + timedelta(days=10)).isoformat(),
        })
        self.assertEqual(resp.status_code, 404)
        self.invoice_b.refresh_from_db()
        self.assertEqual(self.invoice_b.invoice_number, 'B-0001')

    def test_cannot_delete_another_companys_invoice(self):
        self.http.post(reverse('delete_invoice'), {'invoice_id': self.invoice_b.id})
        self.assertTrue(Invoice.objects.filter(id=self.invoice_b.id).exists())

    def test_cannot_record_payment_on_another_companys_invoice(self):
        resp = self.http.post(reverse('record_invoice_payment'), {
            'invoice_id': self.invoice_b.id,
            'amount': '10.00',
        })
        self.assertEqual(resp.json()['success'], False)
        self.invoice_b.refresh_from_db()
        self.assertEqual(self.invoice_b.amount_paid, Decimal('0.00'))

    def test_cannot_download_another_companys_invoice_pdf(self):
        resp = self.http.get(reverse('invoice_pdf', args=[self.invoice_b.id]))
        self.assertEqual(resp.status_code, 404)

    def test_cannot_delete_another_companys_supplier(self):
        self.http.post(reverse('delete_supplier'), {'supplier_id': self.supplier_b.id})
        self.assertTrue(Supplier.objects.filter(id=self.supplier_b.id).exists())

    def test_cannot_delete_another_companys_supply(self):
        self.http.post(reverse('delete_supply'), {'supply_id': self.supply_b.id})
        self.assertTrue(Supply.objects.filter(id=self.supply_b.id).exists())

    def test_cannot_delete_another_companys_agent(self):
        self.http.post(reverse('delete_agent'), {'agent_id': self.agent_b.id})
        self.assertTrue(Agent.objects.filter(id=self.agent_b.id).exists())

    def test_agent_role_from_other_company_is_ignored_not_leaked(self):
        """Si A crée un agent en réutilisant l'ID d'un rôle appartenant à B,
        le rôle de B ne doit pas lui être assigné (il doit être ignoré)."""
        resp = self.http.post(reverse('add_agent'), {
            'name': 'Nouvel agent de A',
            'role_id': self.role_b.id,
        })
        self.assertEqual(resp.json()['success'], True)
        new_agent = Agent.objects.get(id=resp.json()['agent_id'], company=self.company_a)
        self.assertIsNone(new_agent.role)  # le rôle de B n'a pas fuité vers A

    def test_cannot_delete_another_companys_agent_role(self):
        self.http.post(reverse('delete_agent_role'), {'role_id': self.role_b.id})
        self.assertTrue(AgentRole.objects.filter(id=self.role_b.id).exists())


class ListViewIsolationTests(MultiTenantFixtureMixin, TestCase):
    """Les pages de listing doivent afficher uniquement les données de
    l'entreprise connectée — jamais un nom/identifiant appartenant à une autre."""

    def test_dashboard_does_not_leak_other_company_name(self):
        resp = self.http.get(reverse('dashboard'))
        content = resp.content.decode('utf-8')
        self.assertIn('Entreprise A', content)
        self.assertNotIn('Entreprise B', content)

    def test_client_list_does_not_leak_other_company_client(self):
        resp = self.http.get(reverse('list_clients'))
        content = resp.content.decode('utf-8')
        self.assertIn('Client de A', content)
        self.assertNotIn('Client de B', content)

    def test_product_list_does_not_leak_other_company_product(self):
        resp = self.http.get(reverse('list_products'))
        content = resp.content.decode('utf-8')
        self.assertIn('Produit de A', content)
        self.assertNotIn('Produit de B', content)

    def test_supplier_list_does_not_leak_other_company_supplier(self):
        resp = self.http.get(reverse('list_suppliers'))
        content = resp.content.decode('utf-8')
        self.assertNotIn('Fournisseur de B', content)

    def test_sale_list_does_not_leak_other_company_sale(self):
        resp = self.http.get(reverse('list_sales'))
        content = resp.content.decode('utf-8')
        self.assertNotIn('Client de B', content)

    def test_invoice_list_does_not_leak_other_company_invoice(self):
        resp = self.http.get(reverse('list_invoices'))
        content = resp.content.decode('utf-8')
        self.assertNotIn('B-0001', content)

    def test_agent_list_does_not_leak_other_company_agent(self):
        resp = self.http.get(reverse('list_agents'))
        content = resp.content.decode('utf-8')
        self.assertNotIn('Agent de B', content)

