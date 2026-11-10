import unittest
from admin_access import email_allowed, _secret

class AdminAccessTest(unittest.TestCase):
    def test_allowlist(self):
        self.assertTrue(email_allowed('Owner@Example.com', 'other@example.com, owner@example.com'))
        self.assertFalse(email_allowed('owner@example.com.attacker.com', 'owner@example.com'))
        self.assertFalse(email_allowed('', 'owner@example.com'))
        self.assertFalse(email_allowed('owner@example.com', ''))
    def test_missing_secret_fails_closed(self):
        self.assertEqual(_secret({}, 'ADMIN_PASSWORD'), '')
        self.assertEqual(_secret({'ADMIN_PASSWORD': '  secret  '}, 'ADMIN_PASSWORD'), 'secret')

if __name__ == '__main__': unittest.main()
