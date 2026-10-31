"""Test configuration for vertical-spine-kit.

Sets the license signing secret so HMAC-signed license keys can be minted
and verified in tests without requiring production env vars.
"""

import os

os.environ.setdefault("LICENSE_SIGNING_SECRET", "test-license-signing-secret-do-not-use-in-production")
