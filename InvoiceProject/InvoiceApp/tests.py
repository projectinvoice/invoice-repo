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

    def test_verify_and_apply_payment_activates_subscription_and_company(self):
        from unittest.mock import patch, MagicMock
        from .models import SubscriptionPayment
        from .views.subscription import _verify_and_apply_payment

        self.assertTrue(self.sub.is_blocked)
        self.assertFalse(self.company.is_active)

        payment = SubscriptionPayment.objects.create(
            company=self.company,
            plan='monthly',
            amount=6000,
            transaction_id='SUB-TEST-12345',
            provider_token='tok_moneyfusion_valid',
            status='pending',
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "statut": True,
            "data": {
                "statut": "paid",
                "moyen": "wave",
                "numeroTransaction": "TXN-98765",
            },
        }

        with patch('InvoiceApp.views.subscription.http_requests.get', return_value=mock_resp):
            _verify_and_apply_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'success')
        self.assertEqual(payment.payment_method, 'wave')
        self.assertEqual(payment.operator_id, 'TXN-98765')

        self.company.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertTrue(self.company.is_active)
        self.assertFalse(self.sub.is_blocked)
        self.assertEqual(self.sub.status, 'active')

    def test_moneyfusion_webhook_session_completed_activates_subscription(self):
        from .models import SubscriptionPayment

        self.assertTrue(self.sub.is_blocked)
        self.assertFalse(self.company.is_active)

        payment = SubscriptionPayment.objects.create(
            company=self.company,
            plan='monthly',
            amount=6000,
            transaction_id='SUB-WEBHOOK-12345',
            provider_token='tok_webhook_token',
            status='pending',
        )

        payload = {
            "event": "payin.session.completed",
            "statut": "paid",
            "tokenPay": "tok_webhook_token",
            "numeroTransaction": "TXN-WH-111",
            "moyen": "orange",
            "personal_Info": [{"userId": str(self.company.id), "orderId": "SUB-WEBHOOK-12345"}],
        }

        response = self.client.post(
            reverse('moneyfusion_webhook'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'success')
        self.company.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertTrue(self.company.is_active)
        self.assertFalse(self.sub.is_blocked)
        self.assertEqual(self.sub.status, 'active')


class OfficialPricingAndSellerLimitsTests(TestCase):
    """Vérifications obligatoires pour les nouveaux tarifs et les limites de vendeurs."""

    def setUp(self):
        self.User = get_user_model()
        self.company = self.User.objects.create_user(
            username='company_pricing',
            password='Password123!',
            company_name='Atlas Grossiste SARL',
            default_currency='XOF',
            is_active=True,
        )
        from .models import Subscription, TRIAL_DURATION_DAYS
        from django.utils import timezone
        self.sub = Subscription.objects.create(
            company=self.company,
            plan='essential_monthly',
            trial_end_date=timezone.now() + timezone.timedelta(days=TRIAL_DURATION_DAYS),
        )
        self.client.force_login(self.company)

    def test_official_plan_prices_in_models(self):
        """Vérifie que les tarifs officiels sont exactement ceux exigés :
        - Essentiel : 6 000 FCFA/mois, 50 000 FCFA/an
        - Business : 8 000 FCFA/mois, 60 000 FCFA/an"""
        from .models import SUBSCRIPTION_PLAN_PRICES
        self.assertEqual(SUBSCRIPTION_PLAN_PRICES['essential_monthly'], Decimal('6000'))
        self.assertEqual(SUBSCRIPTION_PLAN_PRICES['essential_annual'], Decimal('50000'))
        self.assertEqual(SUBSCRIPTION_PLAN_PRICES['business_monthly'], Decimal('8000'))
        self.assertEqual(SUBSCRIPTION_PLAN_PRICES['business_annual'], Decimal('60000'))

    def test_essential_plan_blocks_eleventh_seller(self):
        """Le plan Essentiel autorise jusqu'à 10 vendeurs et refuse le 11e côté serveur."""
        from .models import Agent
        # Création de 10 vendeurs
        for i in range(1, 11):
            Agent.objects.create(
                company=self.company,
                name=f"Vendeur {i}",
                phone=f"77000000{i:02d}",
            )

        self.assertEqual(self.company.agents.count(), 10)

        # Tentative d'ajout du 11e vendeur via l'API add_agent
        resp = self.client.post(reverse('add_agent'), {
            'name': 'Vendeur Onzieme',
            'phone': '779999999',
        })
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn("plan Essentiel autorise au maximum 10 vendeurs", data['error'])
        self.assertIn("Business", data['error'])
        self.assertEqual(self.company.agents.count(), 10)

    def test_business_plan_allows_more_than_ten_sellers(self):
        """Le plan Business permet de dépasser la limite de 10 vendeurs."""
        from .models import Agent
        self.sub.plan = 'business_monthly'
        self.sub.save(update_fields=['plan'])

        for i in range(1, 11):
            Agent.objects.create(
                company=self.company,
                name=f"Vendeur {i}",
                phone=f"77000000{i:02d}",
            )

        # Ajout du 11e vendeur sur plan Business
        resp = self.client.post(reverse('add_agent'), {
            'name': 'Vendeur Onzieme',
            'phone': '779999999',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(self.company.agents.count(), 11)

    def test_pricing_page_public_accessibility_and_content(self):
        """La page pricing.html est accessible publiquement et contient les deux plans,
        les tarifs officiels en FCFA, le comparatif et la FAQ."""
        self.client.logout()
        resp = self.client.get(reverse('pricing'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'pricing.html')
        content = resp.content.decode('utf-8')

        # Présence des deux plans officiels
        self.assertIn("Essentiel", content)
        self.assertIn("Business", content)

        # Présence des tarifs de référence
        self.assertIn("6 000", content)
        self.assertIn("50 000", content)
        self.assertIn("8 000", content)
        self.assertIn("60 000", content)
        self.assertIn("FCFA", content)

        # Présence de la limite de 10 vendeurs
        self.assertIn("10 vendeurs", content)

        # Présence de la FAQ et des 7 questions fondamentales
        self.assertIn("Foire aux questions", content)
        self.assertIn("Quelle est la différence entre les plans Essentiel et Business ?", content)
        self.assertIn("Qui paie l'abonnement ?", content)
        self.assertIn("onzième vendeur", content)

    def test_pricing_page_currency_context(self):
        """La page de tarification respecte le paramètre de devise ou la devise de l'entreprise."""
        resp_eur = self.client.get(reverse('pricing') + '?currency=EUR')
        self.assertEqual(resp_eur.status_code, 200)
        self.assertEqual(resp_eur.context['selected_currency'], 'EUR')

        resp_usd = self.client.get(reverse('pricing') + '?currency=USD')
        self.assertEqual(resp_usd.status_code, 200)
        self.assertEqual(resp_usd.context['selected_currency'], 'USD')

    def test_product_pricing_unaffected_by_subscription_changes(self):
        """Vérifie que les prix des produits commerciaux restent intègres et non affectés."""
        from .models import Product
        prod = Product.objects.create(
            company=self.company,
            name='Produit Commercial Normal',
            price=Decimal('1500.00'),
            currency='XOF',
            stock_quantity=50,
        )
        self.assertEqual(prod.price, Decimal('1500.00'))
        self.assertEqual(prod.formatted_price, '1 500 FCFA')


class InvoiceEnhancementTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.company = self.User.objects.create_user(
            username='company_a', password='password123',
            company_name='Entreprise A', company_email='contact@entreprise-a.com',
            phone='+221770000000', agent_login_code='COMPA'
        )
        self.other_company = self.User.objects.create_user(
            username='company_b', password='password123',
            company_name='Entreprise B', company_email='contact@entreprise-b.com',
            phone='+221779999999', agent_login_code='COMPB'
        )

        from .models import Client, Product, Sale, SaleItem, Invoice, Agent, AgentRole
        self.client_a = Client.objects.create(
            company=self.company, name='Moussa Diop',
            shop_name='Boutique Keur Moussa',
            phone='+221771234567', email='moussa@example.com',
            address='Dakar Plateau'
        )
        self.product_1 = Product.objects.create(
            company=self.company, name='Sac de Riz 50kg',
            price=Decimal('17500.00'), currency='XOF', stock_quantity=100
        )
        self.product_2 = Product.objects.create(
            company=self.company, name='Bidon Huile 5L',
            price=Decimal('5000.00'), currency='XOF', stock_quantity=50
        )

        self.role = AgentRole.objects.create(company=self.company, name='Vendeur')
        self.agent = Agent.objects.create(
            company=self.company, name='Agent Amadou', role=self.role, is_active=True
        )
        self.agent.set_pin('1234')
        self.agent.save()

        # Création d'une vente et facture pour l'Entreprise A
        self.sale = Sale.objects.create(
            company=self.company, client=self.client_a, agent=self.agent,
            currency='XOF', total_price=Decimal('45000.00')
        )
        SaleItem.objects.create(
            sale=self.sale, product=self.product_1, quantity=2,
            unit_price=Decimal('17500.00'), total_price=Decimal('35000.00'), currency='XOF'
        )
        SaleItem.objects.create(
            sale=self.sale, product=self.product_2, quantity=2,
            unit_price=Decimal('5000.00'), total_price=Decimal('10000.00'), currency='XOF'
        )

        from django.utils import timezone
        from datetime import timedelta
        self.invoice = Invoice.objects.create(
            company=self.company, sale=self.sale,
            invoice_number='FAC-2026-TEST01',
            due_date=timezone.now().date() + timedelta(days=15),
            amount_paid=Decimal('20000.00'),
            status='partial'
        )

    def test_invoice_pdf_a5_generation_and_download(self):
        """Vérifie la génération du PDF A5 et son téléchargement."""
        from .views.invoices import _build_invoice_pdf_bytes
        pdf_bytes = _build_invoice_pdf_bytes(self.invoice)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

        # Téléchargement via l'URL admin
        self.client.force_login(self.company)
        resp = self.client.get(reverse('invoice_pdf', args=[self.invoice.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn(f'filename="{self.invoice.invoice_number}.pdf"', resp['Content-Disposition'])

    def test_invoice_pdf_multi_item_pagination(self):
        """Vérifie que la pagination A5 gère sans crash un grand nombre d'articles."""
        from .models import Product, SaleItem
        from .views.invoices import _build_invoice_pdf_bytes

        # Ajouter 15 articles supplémentaires pour forcer le saut de page A5
        for i in range(15):
            prod = Product.objects.create(
                company=self.company, name=f'Produit Divers {i+1}',
                price=Decimal('1000.00'), currency='XOF', stock_quantity=10
            )
            SaleItem.objects.create(
                sale=self.sale, product=prod, quantity=1,
                unit_price=Decimal('1000.00'), total_price=Decimal('1000.00'), currency='XOF'
            )

        pdf_bytes = _build_invoice_pdf_bytes(self.invoice)
        self.assertTrue(len(pdf_bytes) > 2000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_admin_send_invoice_email_success(self):
        """L'administrateur peut envoyer la facture par email avec la pièce jointe PDF A5."""
        from django.core import mail
        self.client.force_login(self.company)
        mail.outbox.clear()

        resp = self.client.post(
            reverse('send_invoice_email', args=[self.invoice.id]),
            {'recipient_email': 'client.test@domaine.com', 'message': 'Paiement attendu sous quinzaine.'}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn("Facture envoyée avec succès", data['message'])

        # Vérification du courriel envoyé
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn(self.invoice.invoice_number, sent_email.subject)
        self.assertIn(self.company.company_name, sent_email.subject)
        self.assertEqual(sent_email.to, ['client.test@domaine.com'])
        self.assertIn('Paiement attendu sous quinzaine.', sent_email.body)
        self.assertEqual(len(sent_email.attachments), 1)
        att_name, att_bytes, att_mime = sent_email.attachments[0]
        self.assertEqual(att_name, f"Facture_{self.invoice.invoice_number}.pdf")
        self.assertEqual(att_mime, 'application/pdf')
        self.assertTrue(att_bytes.startswith(b'%PDF'))

    def test_admin_send_invoice_email_tenant_isolation(self):
        """Une autre entreprise ne peut pas envoyer ou accéder à la facture de l'entreprise A."""
        self.client.force_login(self.other_company)
        resp = self.client.post(
            reverse('send_invoice_email', args=[self.invoice.id]),
            {'recipient_email': 'hacker@example.com'}
        )
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertFalse(data['success'])

    def test_admin_send_invoice_email_validation(self):
        """Rejet en cas d'adresse email invalide ou vide."""
        self.client.force_login(self.company)
        resp = self.client.post(
            reverse('send_invoice_email', args=[self.invoice.id]),
            {'recipient_email': 'pas-un-email'}
        )
        self.assertEqual(resp.status_code, 500)
        self.assertFalse(resp.json()['success'])

        resp_empty = self.client.post(
            reverse('send_invoice_email', args=[self.invoice.id]),
            {'recipient_email': ''}
        )
        self.assertEqual(resp_empty.status_code, 400)
        self.assertFalse(resp_empty.json()['success'])

    def test_vendor_send_invoice_email_success(self):
        """Un vendeur connecté peut envoyer par email la facture de son entreprise."""
        from django.core import mail
        mail.outbox.clear()

        # Connexion de l'agent dans la session
        session = self.client.session
        session['agent_id'] = self.agent.id
        session.save()

        resp = self.client.post(
            reverse('vendor_send_invoice_email', args=[self.invoice.id]),
            {'recipient_email': 'client.vendeur@domaine.com'}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ['client.vendeur@domaine.com'])
        self.assertEqual(len(sent.attachments), 1)

    def test_vendor_send_invoice_email_tenant_isolation(self):
        """Un agent d'une autre entreprise ne peut pas envoyer la facture de l'entreprise A."""
        from .models import AgentRole, Agent
        other_role = AgentRole.objects.create(company=self.other_company, name='Vendeur')
        other_agent = Agent.objects.create(company=self.other_company, name='Agent B', role=other_role, is_active=True)

        session = self.client.session
        session['agent_id'] = other_agent.id
        session.save()

        resp = self.client.post(
            reverse('vendor_send_invoice_email', args=[self.invoice.id]),
            {'recipient_email': 'cible@domaine.com'}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()['success'])

    def test_vendor_add_sale_returns_enriched_post_sale_payload(self):
        """Vérifie que la création d'une vente par un vendeur renvoie les données nécessaires pour le partage immédiat."""
        from .models import AgentStock
        AgentStock.objects.create(agent=self.agent, product=self.product_1, quantity=10, unit_price=Decimal('17500.00'))

        session = self.client.session
        session['agent_id'] = self.agent.id
        session.save()

        sale_items = json.dumps([{'product_id': self.product_1.id, 'quantity': 1}])
        resp = self.client.post(reverse('vendor_add_sale'), {
            'client_id': self.client_a.id,
            'sale_items': sale_items,
            'payment_type': 'full'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('invoice_number', data)
        self.assertIn('client_phone', data)
        self.assertEqual(data['client_phone'], '+221771234567')
        self.assertIn('formatted_total_price', data)
        self.assertIn('formatted_balance_due', data)
        self.assertTrue(data['is_paid'])


class WhatsAppCloudApiTests(TestCase):
    def setUp(self):
        from unittest.mock import patch
        self.User = get_user_model()
        self.company = self.User.objects.create_user(
            username='wa_company_a', password='password123',
            company_name='Keur Entreprise', phone='+221770000000',
            agent_login_code='WACOMP'
        )
        self.other_company = self.User.objects.create_user(
            username='wa_company_b', password='password123',
            company_name='Autre Entreprise', phone='+221779999999'
        )

        from .models import Client, Product, Sale, SaleItem, Invoice, Agent, AgentRole
        self.client_obj = Client.objects.create(
            company=self.company, name='Babacar Ndiaye',
            phone='+221 77 987 65 43', email='babacar@example.com'
        )
        self.product = Product.objects.create(
            company=self.company, name='Huile 5L',
            price=Decimal('5000.00'), currency='XOF', stock_quantity=20
        )
        self.role = AgentRole.objects.create(company=self.company, name='Commercial')
        self.agent = Agent.objects.create(
            company=self.company, name='Vendeur Wa', role=self.role, is_active=True
        )

        self.sale = Sale.objects.create(
            company=self.company, client=self.client_obj, agent=self.agent,
            currency='XOF', total_price=Decimal('10000.00')
        )
        SaleItem.objects.create(
            sale=self.sale, product=self.product, quantity=2,
            unit_price=Decimal('5000.00'), total_price=Decimal('10000.00'), currency='XOF'
        )
        from django.utils import timezone
        from datetime import timedelta
        self.invoice = Invoice.objects.create(
            company=self.company, sale=self.sale,
            invoice_number='FAC-WA-001',
            due_date=timezone.now().date() + timedelta(days=7),
            amount_paid=Decimal('10000.00'),
            status='paid'
        )

    def test_clean_phone_for_whatsapp(self):
        """Vérifie le formatage des numéros de téléphone pour l'API Meta."""
        from .services.whatsapp import clean_phone_for_whatsapp
        self.assertEqual(clean_phone_for_whatsapp('77 123 45 67'), '221771234567')
        self.assertEqual(clean_phone_for_whatsapp('+221 77 123 45 67'), '221771234567')
        self.assertEqual(clean_phone_for_whatsapp('+33 6 12 34 56 78'), '33612345678')
        self.assertEqual(clean_phone_for_whatsapp(''), '')

    def test_whatsapp_webhook_get_challenge_verification(self):
        """Vérifie l'échange de vérification de webhook Meta (GET)."""
        from django.conf import settings
        token = settings.WHATSAPP_VERIFY_TOKEN

        # Succès : token valide
        resp = self.client.get(reverse('whatsapp_webhook') + f"?hub.mode=subscribe&hub.verify_token={token}&hub.challenge=test_challenge_12345")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode('utf-8'), 'test_challenge_12345')

        # Échec : token invalide
        resp_bad = self.client.get(reverse('whatsapp_webhook') + "?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=test")
        self.assertEqual(resp_bad.status_code, 403)

    def test_whatsapp_webhook_post_delivery_statuses(self):
        """Vérifie la mise à jour automatique des statuts 'delivered' et 'read' via le webhook."""
        self.invoice.whatsapp_message_id = 'wamid.TEST_MESSAGE_ID_001'
        self.invoice.whatsapp_delivery_status = 'sent'
        self.invoice.save()

        # Événement 1 : Remis sur le téléphone (delivered)
        payload_delivered = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.TEST_MESSAGE_ID_001",
                            "status": "delivered",
                            "timestamp": "1710000000"
                        }]
                    }
                }]
            }]
        }
        resp = self.client.post(
            reverse('whatsapp_webhook'),
            data=json.dumps(payload_delivered),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.whatsapp_delivery_status, 'delivered')
        self.assertIsNotNone(self.invoice.whatsapp_delivered_at)
        self.assertEqual(self.invoice.whatsapp_status_label, '✓✓ Remis')

        # Événement 2 : Lu par le destinataire (read)
        payload_read = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.TEST_MESSAGE_ID_001",
                            "status": "read",
                            "timestamp": "1710000100"
                        }]
                    }
                }]
            }]
        }
        resp_read = self.client.post(
            reverse('whatsapp_webhook'),
            data=json.dumps(payload_read),
            content_type="application/json"
        )
        self.assertEqual(resp_read.status_code, 200)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.whatsapp_delivery_status, 'read')
        self.assertIsNotNone(self.invoice.whatsapp_read_at)
        self.assertEqual(self.invoice.whatsapp_status_label, '✓✓ Lu')

    def test_admin_send_whatsapp_client_fallback_when_unconfigured(self):
        """Si l'API Cloud n'a pas de token configuré, le backend renvoie le signal client_fallback."""
        self.client.force_login(self.company)
        with self.settings(WHATSAPP_TOKEN='', WHATSAPP_PHONE_NUMBER_ID=''):
            resp = self.client.post(
                reverse('send_invoice_whatsapp', args=[self.invoice.id]),
                {'phone': '771234567'}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['success'])
            self.assertEqual(data['mode'], 'client_fallback')

    def test_admin_send_whatsapp_cloud_api_success(self):
        """Si l'API Cloud est configurée, le backend envoie directement le PDF via Meta."""
        from unittest.mock import patch, MagicMock
        self.client.force_login(self.company)

        with self.settings(WHATSAPP_TOKEN='mock_meta_token', WHATSAPP_PHONE_NUMBER_ID='123456789'):
            # Mock de requests.post pour l'upload media et l'envoi de message
            def mock_requests_post(url, *args, **kwargs):
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                if '/media' in url:
                    mock_resp.json.return_value = {"id": "meta_media_98765"}
                elif '/messages' in url:
                    mock_resp.json.return_value = {"messages": [{"id": "wamid.NEW_META_WAMID_123"}]}
                return mock_resp

            with patch('requests.post', side_effect=mock_requests_post):
                resp = self.client.post(
                    reverse('send_invoice_whatsapp', args=[self.invoice.id]),
                    {'phone': '77 987 65 43'}
                )
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertTrue(data['success'])
                self.assertEqual(data['mode'], 'cloud_api')
                self.assertEqual(data['message_id'], 'wamid.NEW_META_WAMID_123')

                self.invoice.refresh_from_db()
                self.assertEqual(self.invoice.whatsapp_message_id, 'wamid.NEW_META_WAMID_123')
                self.assertEqual(self.invoice.whatsapp_delivery_status, 'sent')
                self.assertEqual(self.invoice.whatsapp_status_label, '✓ Envoyé')

    def test_whatsapp_tenant_isolation(self):
        """Une autre entreprise ne peut pas envoyer la facture d'une entreprise différente."""
        self.client.force_login(self.other_company)
        resp = self.client.post(
            reverse('send_invoice_whatsapp', args=[self.invoice.id]),
            {'phone': '770000000'}
        )
        self.assertEqual(resp.status_code, 404)

    def test_whatsapp_ui_hidden_when_unconfigured(self):
        """Quand la clé WHATSAPP_TOKEN n'est pas définie dans l'environnement, la section WhatsApp est cachée."""
        self.client.force_login(self.company)
        with self.settings(WHATSAPP_TOKEN=''):
            resp = self.client.get(reverse('list_invoices'))
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.context.get('whatsapp_enabled', False))
            self.assertNotContains(resp, "Partager sur WhatsApp")

    def test_whatsapp_ui_visible_when_token_configured(self):
        """Quand la clé WHATSAPP_TOKEN est présente dans l'environnement, la section WhatsApp est affichée."""
        self.client.force_login(self.company)
        with self.settings(WHATSAPP_TOKEN='test_token_secret_123'):
            resp = self.client.get(reverse('list_invoices'))
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.context.get('whatsapp_enabled', False))
            self.assertContains(resp, "Partager sur WhatsApp")


class AuditSecurityAndDataIntegrityTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.company_a = self.User.objects.create_user(
            username='company_a@test.com', email='company_a@test.com', password='password123',
            company_name='Company Alpha', default_currency='EUR'
        )
        self.company_b = self.User.objects.create_user(
            username='company_b@test.com', email='company_b@test.com', password='password123',
            company_name='Company Beta', default_currency='EUR'
        )
        self.client_a = Client.objects.create(company=self.company_a, name='Client A')
        self.product_a = Product.objects.create(company=self.company_a, name='Product A', price='20.00', stock_quantity=10)
        self.client_b = Client.objects.create(company=self.company_b, name='Client B')

    def test_delete_client_with_sales(self):
        """Un client (même avec des ventes associées) peut être supprimé."""
        self.client.force_login(self.company_a)
        sale = Sale.objects.create(company=self.company_a, client=self.client_a)
        SaleItem.objects.create(sale=sale, product=self.product_a, quantity=2, unit_price='20.00')

        resp = self.client.post(reverse('delete_client'), {'client_id': self.client_a.id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertFalse(Client.objects.filter(id=self.client_a.id).exists())

    def test_delete_product_with_sales(self):
        """Un produit (même lié à des ventes passées) peut être supprimé."""
        self.client.force_login(self.company_a)
        sale = Sale.objects.create(company=self.company_a, client=self.client_a)
        SaleItem.objects.create(sale=sale, product=self.product_a, quantity=1, unit_price='20.00')

        resp = self.client.post(reverse('delete_product'), {'product_id': self.product_a.id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertFalse(Product.objects.filter(id=self.product_a.id).exists())

    def test_delete_supplier_with_supplies(self):
        """Un fournisseur (même avec des approvisionnements) peut être supprimé."""
        from .models import Supplier, Supply
        supplier = Supplier.objects.create(company=self.company_a, name='Supplier X')
        Supply.objects.create(company=self.company_a, supplier=supplier)

        self.client.force_login(self.company_a)
        resp = self.client.post(reverse('delete_supplier'), {'supplier_id': supplier.id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertFalse(Supplier.objects.filter(id=supplier.id).exists())

    def test_delete_agent_with_stock_or_sales(self):
        """Un agent détenant du stock ou lié à des ventes peut être supprimé et son stock retourne en magasin."""
        from .models import Agent, AgentStock
        agent = Agent.objects.create(company=self.company_a, name='Agent Mohamed')
        AgentStock.objects.create(agent=agent, product=self.product_a, quantity=5, unit_price='20.00')

        self.client.force_login(self.company_a)
        resp = self.client.post(reverse('delete_agent'), {'agent_id': agent.id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertFalse(Agent.objects.filter(id=agent.id).exists())
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock_quantity, 15)

    def test_delete_invoice_with_recorded_payments(self):
        """Une facture ayant des règlements partiels ou complets peut être supprimée."""
        from .models import Invoice, Payment
        from django.utils import timezone
        sale = Sale.objects.create(company=self.company_a, client=self.client_a)
        SaleItem.objects.create(sale=sale, product=self.product_a, quantity=2, unit_price='20.00')
        invoice = Invoice.objects.create(
            company=self.company_a, sale=sale, invoice_number='FAC-2026-00001',
            due_date=timezone.now().date(), amount_paid=Decimal('20.00'), status='partial'
        )
        Payment.objects.create(invoice=invoice, amount=Decimal('20.00'), note='Acompte')

        self.client.force_login(self.company_a)
        resp = self.client.post(reverse('delete_invoice'), {'invoice_id': invoice.id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertFalse(Invoice.objects.filter(id=invoice.id).exists())

    def test_tenant_isolation_on_cross_company_delete(self):
        """Une entreprise A ne peut pas supprimer un client appartenant à une entreprise B."""
        self.client.force_login(self.company_a)
        resp = self.client.post(reverse('delete_client'), {'client_id': self.client_b.id})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Client.objects.filter(id=self.client_b.id).exists())

    def test_delete_sale_replenishes_vendor_stock_when_agent_sale(self):
        """Quand une vente réalisée par un vendeur est annulée/supprimée, le stock retourne chez le vendeur."""
        from .models import Agent, AgentStock
        agent = Agent.objects.create(company=self.company_a, name='Vendor Ali')
        agent_stock = AgentStock.objects.create(agent=agent, product=self.product_a, quantity=2, unit_price='20.00')
        sale = Sale.objects.create(company=self.company_a, client=self.client_a, agent=agent)
        SaleItem.objects.create(sale=sale, product=self.product_a, quantity=3, unit_price='20.00')

        self.client.force_login(self.company_a)
        resp = self.client.post(reverse('delete_sale'), {'sale_id': sale.id})
        self.assertEqual(resp.status_code, 200)
        agent_stock.refresh_from_db()
        self.assertEqual(agent_stock.quantity, 5)  # 2 restants + 3 récrédités


    def test_delete_supply_engine_role_and_stock_loads(self):
        """Vérifie que les suppressions d'approvisionnements, engins, rôles, chargements et retours fonctionnent sans blocage."""
        from .models import Supplier, Supply, SupplyItem, Engine, AgentRole, Agent, AgentStock, StockLoad, StockLoadItem, StockReturn, StockReturnItem
        self.client.force_login(self.company_a)

        # 1. Approvisionnement (même si le stock a été partiellement vendu ensuite)
        supplier = Supplier.objects.create(company=self.company_a, name='Fournisseur Global')
        supply = Supply.objects.create(company=self.company_a, supplier=supplier)
        SupplyItem.objects.create(supply=supply, product=self.product_a, quantity=50, unit_price='10.00')
        resp_supply = self.client.post(reverse('delete_supply'), {'supply_id': supply.id})
        self.assertEqual(resp_supply.status_code, 200)
        self.assertTrue(resp_supply.json()['success'])
        self.assertFalse(Supply.objects.filter(id=supply.id).exists())

        # 2. Engin lié à un agent
        engine = Engine.objects.create(company=self.company_a, name='Tricycle 01', status='active')
        role = AgentRole.objects.create(company=self.company_a, name='Chauffeur-Livreur')
        agent = Agent.objects.create(company=self.company_a, name='Agent Test', role=role, engine=engine)

        resp_engine = self.client.post(reverse('delete_engine'), {'engine_id': engine.id})
        self.assertEqual(resp_engine.status_code, 200)
        self.assertTrue(resp_engine.json()['success'])
        self.assertFalse(Engine.objects.filter(id=engine.id).exists())

        # 3. Rôle lié à un agent
        resp_role = self.client.post(reverse('delete_agent_role'), {'role_id': role.id})
        self.assertEqual(resp_role.status_code, 200)
        self.assertTrue(resp_role.json()['success'])
        self.assertFalse(AgentRole.objects.filter(id=role.id).exists())

        # 4. Chargement de stock (même si le vendeur a déjà vendu une partie)
        AgentStock.objects.create(agent=agent, product=self.product_a, quantity=3, unit_price='20.00')
        load = StockLoad.objects.create(company=self.company_a, agent=agent)
        StockLoadItem.objects.create(load=load, product=self.product_a, quantity=10, unit_price='20.00')
        resp_load = self.client.post(reverse('delete_stock_load'), {'load_id': load.id})
        self.assertEqual(resp_load.status_code, 200)
        self.assertTrue(resp_load.json()['success'])
        self.assertFalse(StockLoad.objects.filter(id=load.id).exists())

        # 5. Retour de stock
        stock_return = StockReturn.objects.create(company=self.company_a, agent=agent)
        StockReturnItem.objects.create(stock_return=stock_return, product=self.product_a, quantity=5)
        resp_return = self.client.post(reverse('delete_stock_return'), {'return_id': stock_return.id})
        self.assertEqual(resp_return.status_code, 200)
        self.assertTrue(resp_return.json()['success'])
        self.assertFalse(StockReturn.objects.filter(id=stock_return.id).exists())


    def test_independent_deletion_client_sale_invoice(self):
        """Vérifie que supprimer un client ne supprime ni la vente ni la facture, et que supprimer une vente ne supprime pas la facture."""
        from .models import Invoice
        from django.utils import timezone
        self.client.force_login(self.company_a)

        sale = Sale.objects.create(company=self.company_a, client=self.client_a)
        SaleItem.objects.create(sale=sale, product=self.product_a, quantity=2, unit_price='20.00')
        sale.save()
        invoice = Invoice.objects.create(
            company=self.company_a, sale=sale, invoice_number='FAC-IND-001',
            due_date=timezone.now().date(), amount_paid=Decimal('40.00'), status='paid'
        )

        # 1. Suppression du client -> le client est supprimé, mais la vente et la facture restent intactes
        resp_c = self.client.post(reverse('delete_client'), {'client_id': self.client_a.id})
        self.assertEqual(resp_c.status_code, 200)
        self.assertFalse(Client.objects.filter(id=self.client_a.id).exists())
        self.assertTrue(Sale.objects.filter(id=sale.id).exists())
        self.assertTrue(Invoice.objects.filter(id=invoice.id).exists())
        self.assertEqual(self.client.get(reverse('list_sales')).status_code, 200)
        self.assertEqual(self.client.get(reverse('list_invoices')).status_code, 200)

        # 2. Suppression de la vente -> la vente est supprimée, mais la facture reste intacte et son PDF reste téléchargeable
        resp_s = self.client.post(reverse('delete_sale'), {'sale_id': sale.id})
        self.assertEqual(resp_s.status_code, 200)
        self.assertFalse(Sale.objects.filter(id=sale.id).exists())
        self.assertTrue(Invoice.objects.filter(id=invoice.id).exists())
        self.assertEqual(self.client.get(reverse('list_sales')).status_code, 200)
        self.assertEqual(self.client.get(reverse('list_invoices')).status_code, 200)

        resp_pdf = self.client.get(reverse('invoice_pdf', args=[invoice.id]))
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(self.client.get(reverse('list_invoices')).status_code, 200)

        # 3. Suppression de la facture -> la facture est supprimée individuellement
        resp_i = self.client.post(reverse('delete_invoice'), {'invoice_id': invoice.id})
        self.assertEqual(resp_i.status_code, 200)
        self.assertFalse(Invoice.objects.filter(id=invoice.id).exists())


class BrevoEmailMigrationTests(TestCase):
    """Tests de la configuration Brevo et des flux email transactionnels (hors envoi réel)."""

    def setUp(self):
        self.User = get_user_model()
        self.company = self.User.objects.create_user(
            username='brevo-company@example.com',
            email='brevo-company@example.com',
            password='StrongPassword123!',
            company_name='Brevo Test SAS',
            company_email='brevo-company@example.com',
            is_active=True,
        )
        from .models import Subscription, Client, Product, Sale, SaleItem, Invoice
        from django.utils import timezone
        Subscription.objects.create(
            company=self.company,
            plan='monthly',
            trial_end_date=timezone.now() + timezone.timedelta(days=7),
        )
        self.client_obj = Client.objects.create(
            company=self.company,
            name='Client Brevo',
            email='client.brevo@example.com',
        )
        self.product = Product.objects.create(
            company=self.company,
            name='Produit Test Brevo',
            price=Decimal('5000.00'),
            stock_quantity=10,
        )
        self.sale = Sale.objects.create(
            company=self.company,
            client=self.client_obj,
            currency='XOF',
        )
        SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal('5000.00'),
            total_price=Decimal('10000.00'),
            currency='XOF',
        )
        self.sale.save()
        self.invoice = Invoice.objects.create(
            company=self.company,
            sale=self.sale,
            invoice_number='FAC-BREVO-001',
            due_date=timezone.now().date(),
            amount_paid=Decimal('10000.00'),
            status='paid',
        )

    def _mock_brevo_response(self, status_code=201, payload=None):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.status_code = status_code
        data = payload if payload is not None else {'messageId': '<test-brevo-msg-id@brevo.com>'}
        resp.content = json.dumps(data).encode('utf-8')
        resp.text = json.dumps(data)
        resp.json.return_value = data
        return resp

    def test_brevo_settings_configured(self):
        """Vérifie la présence des paramètres Brevo et DEFAULT_FROM_EMAIL dans settings."""
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'BREVO_API_KEY'))
        self.assertTrue(hasattr(settings, 'BREVO_API_URL'))
        self.assertTrue(bool(settings.DEFAULT_FROM_EMAIL))
        self.assertTrue(bool(settings.SUPPORT_EMAIL))

    def test_registration_and_resend_activation_via_brevo_backend(self):
        """Inscription et renvoi d'activation appellent l'API Brevo v3 avec HTML + texte et lien valide."""
        from unittest.mock import patch
        from django.test import override_settings

        mock_resp = self._mock_brevo_response(201)
        with override_settings(
            EMAIL_BACKEND='InvoiceApp.email_backends.BrevoEmailBackend',
            DEFAULT_FROM_EMAIL='co@merchandblock.com',
            BREVO_API_KEY='xkeysib-test-fake-key-for-unit-tests',
        ):
            with patch('InvoiceApp.email_backends.requests.post', return_value=mock_resp) as mock_post:
                resp = self.client.post(reverse('register'), {
                    'company_name': 'Nouvelle Entreprise',
                    'email': 'nouvelle@example.com',
                    'password': 'StrongPassword123!',
                    'password_confirm': 'StrongPassword123!',
                    'default_currency': 'XOF',
                    'subscription_plan': 'monthly',
                })
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertTrue(data['success'])
                self.assertTrue(data['activation_email_sent'])

                self.assertEqual(mock_post.call_count, 1)
                args, kwargs = mock_post.call_args
                req_url = args[0] if len(args) > 0 else kwargs.get('url')
                self.assertEqual(req_url, 'https://api.brevo.com/v3/smtp/email')
                self.assertEqual(kwargs['headers'].get('api-key'), 'xkeysib-test-fake-key-for-unit-tests')
                body = kwargs['json']
                self.assertEqual(body['sender']['email'], 'co@merchandblock.com')
                self.assertEqual(body['to'][0]['email'], 'nouvelle@example.com')
                self.assertIn('Activez votre compte', body['subject'])
                self.assertIn('htmlContent', body)
                self.assertIn('textContent', body)
                self.assertIn('/activer-compte/', body['textContent'])

                resp_resend = self.client.post(reverse('resend_activation_email'), {'email': 'nouvelle@example.com'})
                self.assertEqual(resp_resend.status_code, 200)
                self.assertTrue(resp_resend.json()['success'])
                self.assertEqual(mock_post.call_count, 2)

    def test_forgot_password_via_brevo_backend(self):
        """La réinitialisation du mot de passe envoie le lien via l'API Brevo v3."""
        from unittest.mock import patch
        from django.test import override_settings

        mock_resp = self._mock_brevo_response(201)
        with override_settings(
            EMAIL_BACKEND='InvoiceApp.email_backends.BrevoEmailBackend',
            DEFAULT_FROM_EMAIL='co@merchandblock.com',
            BREVO_API_KEY='xkeysib-test-fake-key-for-unit-tests',
        ):
            with patch('InvoiceApp.email_backends.requests.post', return_value=mock_resp) as mock_post:
                resp = self.client.post(reverse('forgot_password'), {'email': 'brevo-company@example.com'})
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.json()['success'])
                self.assertEqual(mock_post.call_count, 1)
                body = mock_post.call_args.kwargs['json']
                self.assertEqual(body['to'][0]['email'], 'brevo-company@example.com')
                self.assertIn('Réinitialisation', body['subject'])
                self.assertIn('/reinitialiser-mot-de-passe/', body['textContent'])

    def test_send_invoice_email_pdf_and_401_error_via_brevo_backend(self):
        """L'envoi de facture PDF et la gestion d'erreur 401 Brevo fonctionnent correctement."""
        from unittest.mock import patch
        from django.test import override_settings

        self.client.force_login(self.company)
        mock_resp_ok = self._mock_brevo_response(201)
        with override_settings(
            EMAIL_BACKEND='InvoiceApp.email_backends.BrevoEmailBackend',
            DEFAULT_FROM_EMAIL='co@merchandblock.com',
            BREVO_API_KEY='xkeysib-test-fake-key-for-unit-tests',
        ):
            with patch('InvoiceApp.email_backends.requests.post', return_value=mock_resp_ok) as mock_post:
                resp = self.client.post(
                    reverse('send_invoice_email', args=[self.invoice.id]),
                    {'recipient_email': 'client.brevo@example.com', 'message': 'Merci.'},
                )
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.json()['success'])
                body = mock_post.call_args.kwargs['json']
                self.assertEqual(body['sender']['email'], 'co@merchandblock.com')
                self.assertEqual(body['replyTo']['email'], 'brevo-company@example.com')
                self.assertEqual(len(body['attachment']), 1)
                self.assertEqual(body['attachment'][0]['name'], 'Facture_FAC-BREVO-001.pdf')

            mock_resp_401 = self._mock_brevo_response(401, {'message': 'Key not found', 'code': 'unauthorized'})
            with patch('InvoiceApp.email_backends.requests.post', return_value=mock_resp_401):
                resp_err = self.client.post(
                    reverse('send_invoice_email', args=[self.invoice.id]),
                    {'recipient_email': 'client.brevo@example.com'},
                )
                self.assertEqual(resp_err.status_code, 500)
                self.assertFalse(resp_err.json()['success'])
                self.assertIn('BREVO_API_KEY', resp_err.json()['error'])

    def test_contact_form_and_service_status_brevo(self):
        """Le formulaire de contact et /statut-service/ gèrent correctement le backend Brevo."""
        from unittest.mock import patch
        from django.test import override_settings

        mock_resp_ok = self._mock_brevo_response(201)
        with override_settings(
            EMAIL_BACKEND='InvoiceApp.email_backends.BrevoEmailBackend',
            DEFAULT_FROM_EMAIL='co@merchandblock.com',
            SUPPORT_EMAIL='co@merchandblock.com',
            BREVO_API_KEY='xkeysib-test-fake-key-for-unit-tests',
        ):
            with patch('InvoiceApp.email_backends.requests.post', return_value=mock_resp_ok) as mock_post:
                resp = self.client.post(reverse('contact'), {
                    'name': 'Moussa',
                    'email': 'moussa@example.com',
                    'subject': 'Question Brevo',
                    'message': 'Bonjour',
                })
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(mock_post.call_count, 1)
                body = mock_post.call_args.kwargs['json']
                self.assertEqual(body['to'][0]['email'], 'co@merchandblock.com')
                self.assertEqual(body['replyTo']['email'], 'moussa@example.com')

            status_ok = self.client.get(reverse('service_status'))
            self.assertEqual(status_ok.status_code, 200)
            self.assertContains(status_ok, 'Emails transactionnels via Brevo')

        with override_settings(
            EMAIL_BACKEND='InvoiceApp.email_backends.BrevoEmailBackend',
            BREVO_API_KEY='',
        ):
            status_missing = self.client.get(reverse('service_status'))
            self.assertEqual(status_missing.status_code, 200)
            self.assertContains(status_missing, 'BREVO_API_KEY non configur')
