from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import PaymentMethod, PaymentType


class PaymentMethodCrudTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username='testuser', password='123456', company_name='Test Company')
        self.client.force_login(self.user)
        self.payment_type = PaymentType.objects.create(company=self.user, name='Carte')

    def test_edit_existing_payment_method(self):
        payment_method = PaymentMethod.objects.create(
            company=self.user,
            name='Cash',
            payment_type=self.payment_type,
            description='Old desc',
            is_active=True,
        )

        response = self.client.post(reverse('add_payment_method'), {
            'payment_method_id': payment_method.id,
            'name': 'Cash Updated',
            'payment_type_id': self.payment_type.id,
            'description': 'New desc',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        payment_method.refresh_from_db()
        self.assertEqual(payment_method.name, 'Cash Updated')
        self.assertEqual(payment_method.description, 'New desc')
