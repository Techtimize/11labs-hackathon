import time
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from api.ratelimit import RateLimit


class RateLimiting(unittest.TestCase):
    def test_a_client_over_the_window_gets_429(self):
        limiter = RateLimit(limit=2, window=60)
        request = SimpleNamespace(client=SimpleNamespace(host="198.51.100.7"))
        limiter(request)
        limiter(request)
        with self.assertRaises(HTTPException) as caught:
            limiter(request)
        self.assertEqual(caught.exception.status_code, 429)

    def test_clients_are_counted_separately(self):
        limiter = RateLimit(limit=1, window=60)
        limiter(SimpleNamespace(client=SimpleNamespace(host="198.51.100.1")))
        limiter(SimpleNamespace(client=SimpleNamespace(host="198.51.100.2")))

    def test_the_window_expires(self):
        limiter = RateLimit(limit=1, window=0.01)
        request = SimpleNamespace(client=SimpleNamespace(host="198.51.100.9"))
        limiter(request)
        time.sleep(0.02)
        limiter(request)
