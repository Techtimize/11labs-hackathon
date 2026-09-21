import unittest

from fastapi import HTTPException

from security.auth import _bearer


class NonAsciiHeaders(unittest.TestCase):
    """Starlette decodes request headers as latin-1, so bytes above 127 arrive as
    non-ASCII str. httpx refuses to send such a header, so the dependency is called
    directly: hmac.compare_digest raises TypeError on non-ASCII str, which would be a
    500 on an unauthenticated route."""

    def test_bearer_dependency_rejects_rather_than_raising(self):
        dep = _bearer("agent-test-token")
        for header in ("Bearer café", "ÿ" * 40, "Bearer "):
            with self.assertRaises(HTTPException) as caught:
                dep(authorization=header)
            self.assertEqual(caught.exception.status_code, 401)

    def test_correct_token_still_passes(self):
        self.assertIsNone(_bearer("agent-test-token")(authorization="Bearer agent-test-token"))
