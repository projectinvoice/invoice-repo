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

Ils couvrent aussi les 5 fonctions "outils" ajoutées pour l'assistant IA (Gemini
function calling), qui doivent respecter la même règle : une entreprise ne peut
jamais recevoir, même indirectement via l'IA, les données d'une autre entreprise.
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, Client as DjangoTestClient, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import (
    Agent, AgentRole, Client, Engine, Invoice, PaymentMethod, PaymentType,
    Product, Sale, Supplier, Supply,
)
from . import views as invoice_views

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
        self.payment_type_b = PaymentType.objects.create(company=self.company_b, name='Espèces B')
        self.payment_method_b = PaymentMethod.objects.create(
            company=self.company_b, name='Cash B', payment_type=self.payment_type_b,
        )

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

    def test_cannot_delete_another_companys_payment_type(self):
        self.http.post(reverse('delete_payment_type'), {'payment_type_id': self.payment_type_b.id})
        self.assertTrue(PaymentType.objects.filter(id=self.payment_type_b.id).exists())

    def test_cannot_delete_another_companys_payment_method(self):
        self.http.post(reverse('delete_payment_method'), {'payment_method_id': self.payment_method_b.id})
        self.assertTrue(PaymentMethod.objects.filter(id=self.payment_method_b.id).exists())


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


class AiToolFunctionsIsolationTests(MultiTenantFixtureMixin, TestCase):
    """Les 5 fonctions appelées par Gemini (function calling) prennent la société
    comme premier argument Python — jamais depuis les arguments fournis par le
    modèle. On vérifie ici qu'aucune ne peut, de quelque façon que ce soit,
    renvoyer une donnée appartenant à une autre entreprise."""

    def test_get_ventes_only_returns_own_sales(self):
        result = invoice_views._ai_tool_get_ventes(self.company_a, {})
        clients_mentionnes = [v['client'] for v in result['ventes_detaillees']]
        self.assertNotIn('Client de B', clients_mentionnes)

    def test_get_ventes_ignores_attempt_to_target_other_client_name(self):
        """Même si on essaie de filtrer sur le nom d'un client de B, la requête
        reste bornée par company=company_a en amont : aucun résultat ne doit sortir."""
        result = invoice_views._ai_tool_get_ventes(self.company_a, {'client_nom': 'Client de B'})
        self.assertEqual(result['ventes_detaillees'], [])
        self.assertEqual(result['nombre_total_ventes_correspondantes'], 0)

    def test_get_etat_financier_only_counts_own_company(self):
        result = invoice_views._ai_tool_get_etat_financier(self.company_a, {})
        # Le CA de B (100.00 EUR : 2 x 50.00) ne doit apparaître nulle part pour A.
        totals = [row['total'] for row in result['chiffre_affaires_par_devise']]
        self.assertNotIn(100.0, totals)

    def test_get_produits_stock_only_returns_own_products(self):
        result = invoice_views._ai_tool_get_produits_stock(self.company_a, {})
        noms = [p['nom'] for p in result['tous_les_produits']]
        self.assertIn('Produit de A', noms)
        self.assertNotIn('Produit de B', noms)

    def test_get_clients_only_returns_own_clients(self):
        result = invoice_views._ai_tool_get_clients(self.company_a, {})
        noms = [c['nom'] for c in result['meilleurs_clients']]
        self.assertIn('Client de A', noms)
        self.assertNotIn('Client de B', noms)

    def test_get_factures_only_returns_own_invoices(self):
        result = invoice_views._ai_tool_get_factures(self.company_a, {})
        numeros = [f['numero'] for f in result['factures']]
        self.assertNotIn('B-0001', numeros)

    def test_unknown_function_name_is_rejected_safely(self):
        result = invoice_views._ai_run_tool('fonction_inexistante', self.company_a, {})
        self.assertIn('erreur', result)


class AiChatEndpointIsolationTests(MultiTenantFixtureMixin, TestCase):
    """Test de bout en bout de /api/ai-chat/ avec un appel Gemini simulé (mock),
    pour vérifier que la boucle d'exécution des fonctions reste bien bornée à
    l'entreprise connectée, même quand le modèle « demande » explicitement les
    données d'une autre entreprise dans ses arguments de fonction."""

    def _fake_gemini_response(self, status_code=200, json_data=None):
        class FakeResponse:
            def __init__(self, sc, data):
                self.status_code = sc
                self._data = data
            def json(self):
                return self._data
        return FakeResponse(status_code, json_data or {})

    @override_settings(GEMINI_API_KEY='fake-key-for-tests')
    @patch('InvoiceApp.views.ai_assistant.http_requests.post')
    def test_function_call_result_is_scoped_to_logged_in_company(self, mock_post):
        """Le modèle « essaie » de récupérer les ventes en précisant un nom de
        client qui appartient à l'entreprise B. La fonction doit renvoyer une
        liste vide (aucune fuite), car elle est bornée par request.user, pas
        par les arguments envoyés par le modèle."""
        first_call = self._fake_gemini_response(200, {
            'candidates': [{
                'content': {
                    'role': 'model',
                    'parts': [{'functionCall': {'name': 'get_ventes', 'args': {'client_nom': 'Client de B'}}}],
                }
            }]
        })
        second_call = self._fake_gemini_response(200, {
            'candidates': [{
                'content': {'role': 'model', 'parts': [{'text': "Aucune vente trouvée pour ce client."}]}
            }]
        })
        mock_post.side_effect = [first_call, second_call]

        resp = self.http.post(
            reverse('ai_chat_api'),
            data=json.dumps({'message': "Montre-moi les ventes du Client de B", 'contents': []}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # La réponse finale du modèle ne doit contenir aucune trace de données de B.
        self.assertEqual(data['reply'], "Aucune vente trouvée pour ce client.")

        # On isole précisément le RÉSULTAT métier (functionResponse) envoyé au 2e
        # round de Gemini — pas la requête entière, qui contiendra forcément la
        # chaîne "Client de B" puisque c'est l'argument que le modèle a lui-même
        # fourni dans son functionCall (ça, ce n'est pas une fuite, juste l'écho
        # de sa propre question). Ce qui compte : le résultat *calculé* par notre
        # fonction ne doit renvoyer aucune vente de B.
        second_request_payload = mock_post.call_args_list[1].kwargs['json']
        function_response_payloads = [
            part['functionResponse']['response']
            for turn in second_request_payload['contents']
            if turn.get('role') == 'user'
            for part in turn.get('parts', [])
            if 'functionResponse' in part
        ]
        self.assertTrue(function_response_payloads, "Aucun functionResponse trouvé dans la requête envoyée à Gemini")
        for payload in function_response_payloads:
            self.assertEqual(payload.get('ventes_detaillees'), [])
            self.assertNotIn('Client de B', json.dumps(payload))

    @override_settings(GEMINI_API_KEY='')
    def test_ai_chat_disabled_gracefully_without_api_key(self):
        resp = self.http.post(
            reverse('ai_chat_api'),
            data=json.dumps({'message': 'Bonjour', 'contents': []}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('pas encore configuré', resp.json()['reply'])

    def test_ai_chat_requires_authentication(self):
        anonymous = DjangoTestClient()
        resp = anonymous.post(
            reverse('ai_chat_api'),
            data=json.dumps({'message': 'Bonjour', 'contents': []}),
            content_type='application/json',
        )
        self.assertNotEqual(resp.status_code, 200)
