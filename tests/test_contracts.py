"""Generated test_contracts.py template (for scaffold output)."""

TEST_CONTRACTS_TEMPLATE = '''"""Contract tests for vertical-spine-kit (auth + core contracts)."""

import pytest
from fastapi.testclient import TestClient

from tests.contract_tests import AuthContractTestBase

from main import app


class TestVerticalSpineKitContracts(AuthContractTestBase):
    """Contract tests for vertical-spine-kit."""

    @pytest.fixture
    def client(self):
        return TestClient(app)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
'''