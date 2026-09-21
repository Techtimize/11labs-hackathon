import hashlib
import hmac
import time
import unittest

from errors.exceptions import BadSignature
from security.webhook_signature import verify


class Signature(unittest.TestCase):
    def test_valid_stale_and_bad(self):
        body, secret, ts = b'{"x":1}', "sek", int(time.time())
        sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        verify(f"t={ts},v0={sig}", body, secret)
        with self.assertRaises(BadSignature):
            verify(f"t={ts},v0={sig}", b'{"x":2}', secret)
        with self.assertRaises(BadSignature):
            verify(f"t={ts - 4000},v0={sig}", body, secret)


class SignatureNonAscii(unittest.TestCase):
    """A raw client can put bytes above 127 in a header; latin-1 decoding makes them
    non-ASCII str, which hmac.compare_digest refuses to compare."""

    def test_non_ascii_signature_is_a_bad_signature_not_a_crash(self):
        body, secret, ts = b'{"x":1}', "sek", int(time.time())
        for provided in ("café", "ÿ" * 64):
            with self.assertRaises(BadSignature):
                verify(f"t={ts},v0={provided}", body, secret)
