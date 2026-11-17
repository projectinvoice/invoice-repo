from django.test import TestCase


class FaviconTests(TestCase):
    """La favicon est servie à la racine par WhiteNoise (WHITENOISE_ROOT),
    y compris pour un visiteur non connecté, sans passer par une vue Django."""

    def test_favicon_ico_servie_a_la_racine(self):
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 200)
        self.assertIn('icon', response['Content-Type'])
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\x00\x00\x01\x00'))  # signature ICO

    def test_apple_touch_icon_servie_a_la_racine(self):
        response = self.client.get('/apple-touch-icon.png')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\x89PNG'))
