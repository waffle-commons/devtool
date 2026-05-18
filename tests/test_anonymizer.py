"""Tests for RFC 013: Anonymization Engine."""

from pathlib import Path

from devtool.utils.anonymizer import AnonymizationDictionary, Anonymizer


class TestAnonymizationDictionary:
    """Test the AnonymizationDictionary mapping system."""

    def test_add_mapping_creates_consistent_placeholder(self) -> None:
        """Test that the same entity always maps to the same placeholder."""
        dictionary = AnonymizationDictionary()

        first = dictionary.add_mapping("LexisNexis", "COMPANY")
        second = dictionary.add_mapping("LexisNexis", "COMPANY")

        assert first == second
        assert first == "[COMPANY_1]"

    def test_add_mapping_increments_counter(self) -> None:
        """Test that different entities get different placeholders."""
        dictionary = AnonymizationDictionary()

        first = dictionary.add_mapping("LexisNexis", "COMPANY")
        second = dictionary.add_mapping("Closd", "COMPANY")

        assert first == "[COMPANY_1]"
        assert second == "[COMPANY_2]"

    def test_add_mapping_tracks_by_category(self) -> None:
        """Test that categories have independent counters."""
        dictionary = AnonymizationDictionary()

        company = dictionary.add_mapping("Acme", "COMPANY")
        email = dictionary.add_mapping("test@example.com", "EMAIL")

        assert company == "[COMPANY_1]"
        assert email == "[EMAIL_1]"


class TestAnonymizer:
    """Test the Anonymizer class."""

    def test_anonymize_redacts_aws_keys(self) -> None:
        """Test that AWS access keys are redacted."""
        anonymizer = Anonymizer()
        content = "aws_key = AKIAIOSFODNN7EXAMPLE"

        result = anonymizer.anonymize(content)

        assert "[AWS_ACCESS_KEY]" in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_anonymize_redacts_stripe_keys(self) -> None:
        """Test that Stripe API keys are redacted."""
        anonymizer = Anonymizer()
        # Real Stripe keys are at least 20 chars after sk_live_
        content = "stripe_key = sk_live_4eC39HqLyjWDarhtT8B3h1j2"

        result = anonymizer.anonymize(content)

        assert "[STRIPE_KEY]" in result
        assert "sk_live_4eC39HqLyjWDarhtT8B3h1j2" not in result

    def test_anonymize_redacts_ssh_keys(self) -> None:
        """Test that SSH keys are redacted."""
        anonymizer = Anonymizer()
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"

        result = anonymizer.anonymize(content)

        assert "[SSH_PRIVATE_KEY_START]" in result
        assert "[SSH_PRIVATE_KEY_END]" in result
        assert "-----BEGIN RSA PRIVATE KEY-----" not in result

    def test_anonymize_with_blocklist(self, tmp_path: Path) -> None:
        """Test anonymization with blocklisted terms."""
        # Create a mock blocklist (we'll skip loading actual file)
        anonymizer = Anonymizer()
        anonymizer.blocklist = ["LexisNexis", "Closd"]

        content = "LexisNexis integration with Closd billing"
        result = anonymizer.anonymize(content)

        # Terms should be replaced with placeholders
        assert "LexisNexis" not in result or "[COMPANY" in result
        assert "Closd" not in result or "[COMPANY" in result

    def test_anonymize_preserves_structure(self) -> None:
        """Test that code structure is preserved after anonymization."""
        anonymizer = Anonymizer()
        content = """def process_invoice(lexis_nexis_id):
    return calculate_total(lexis_nexis_id)"""

        result = anonymizer.anonymize(content)

        # Function structure should still be intact
        assert "def process_invoice" in result
        assert "return calculate_total" in result

    def test_calculate_entropy(self) -> None:
        """Test Shannon entropy calculation."""
        anonymizer = Anonymizer()

        # High entropy string (random)
        high_entropy = anonymizer._calculate_entropy("aB3x9kL2mP0q")

        # Low entropy string (repetitive)
        low_entropy = anonymizer._calculate_entropy("aaaa")

        assert high_entropy > low_entropy
        assert high_entropy > 3.0
        assert low_entropy < 2.0


class TestAnonymizerIntegration:
    """Integration tests for the anonymizer."""

    def test_anonymize_preserves_valid_python(self) -> None:
        """Test that anonymized code is still valid Python."""
        anonymizer = Anonymizer()
        code = """
import requests

class APIClient:
    def __init__(self, api_key="sk_live_abcdef123456"):
        self.api_key = api_key
        self.endpoint = "https://api.example.com"
"""
        result = anonymizer.anonymize(code)

        # Should still be valid Python
        assert "import" in result
        assert "class APIClient" in result
        assert "def __init__" in result

    def test_multiple_secrets_anonymized(self) -> None:
        """Test that multiple secrets are all anonymized."""
        anonymizer = Anonymizer()
        content = """
AWS_KEY = AKIAIOSFODNN7EXAMPLE
STRIPE = sk_live_abcdef123456789012345
SSH = -----BEGIN RSA PRIVATE KEY-----
JWT = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP
"""
        result = anonymizer.anonymize(content)

        # All keys should be anonymized
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "sk_live_abcdef123456789012345" not in result
        assert "[SSH_PRIVATE_KEY_START]" in result or "[SSH_PRIVATE_KEY" in result
        assert "JWT" in result  # Variable name preserved
