"""Anonymization engine for sanitizing sensitive data before cloud export.

RFC 013: Code Anonymization & Sanitization Engine
"""

import re
from pathlib import Path
from typing import Dict

from rich.console import Console

console = Console()


class AnonymizationDictionary:
    """Manages consistent entity mapping for anonymization."""

    def __init__(self) -> None:
        """Initialize the mapping dictionary."""
        self.mapping: Dict[str, str] = {}
        self.counter: Dict[str, int] = {}

    def add_mapping(self, original: str, category: str) -> str:
        """Add or retrieve a consistent mapping for an entity.

        Args:
            original: The original sensitive entity.
            category: The category (e.g., 'COMPANY', 'DOMAIN', 'EMAIL').

        Returns:
            The replacement placeholder.
        """
        if original in self.mapping:
            return self.mapping[original]

        if category not in self.counter:
            self.counter[category] = 1

        replacement = f"[{category}_{self.counter[category]}]"
        self.mapping[original] = replacement
        self.counter[category] += 1
        return replacement


class Anonymizer:
    """Anonymizes code by replacing PII, secrets, and proprietary terms."""

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize the anonymizer.

        Args:
            config_path: Optional path to .devtool-dictionary.toml file.
        """
        self.dictionary = AnonymizationDictionary()
        self.blocklist = self._load_blocklist(config_path)
        self.ignore_list = self._load_ignore_list()

    def _load_blocklist(self, config_path: Path | None) -> list[str]:
        """Load the blocklist from config file.

        Args:
            config_path: Path to .devtool-dictionary.toml.

        Returns:
            List of terms to redact.
        """
        if config_path is None:
            config_path = Path.home() / ".devtool-dictionary.toml"

        if not config_path.exists():
            return []

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore

        content = config_path.read_text()
        data = tomllib.loads(content)
        return data.get("redact_terms", [])

    def _load_ignore_list(self) -> list[str]:
        """Load patterns to ignore from .devtool-ignore-secrets.

        Returns:
            List of patterns to skip during anonymization.
        """
        ignore_file = Path.cwd() / ".devtool-ignore-secrets"
        if not ignore_file.exists():
            return []

        return [
            line.strip()
            for line in ignore_file.read_text().splitlines()
            if line.strip()
        ]

    def anonymize(self, content: str) -> str:
        """Anonymize code content.

        Args:
            content: The code to anonymize.

        Returns:
            The anonymized code.
        """
        result = content

        # 1. Redact blocklisted terms
        for term in self.blocklist:
            if self._should_ignore(term):
                continue
            replacement = self.dictionary.add_mapping(term, "COMPANY_NAME")
            # Use word boundaries to avoid partial matches
            result = re.sub(r"\b" + re.escape(term) + r"\b", replacement, result)

        # 2. Redact email addresses
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        result = self._replace_matches(result, email_pattern, "EMAIL", self.dictionary)

        # 3. Redact domain names (heuristically)
        domain_pattern = r"\b(?:https?://)?(?:www\.)?([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b"
        result = self._replace_matches(
            result, domain_pattern, "DOMAIN", self.dictionary
        )

        # 4. Redact high-entropy strings (likely secrets/keys)
        result = self._redact_high_entropy(result)

        return result

    def _should_ignore(self, pattern: str) -> bool:
        """Check if pattern is in ignore list.

        Args:
            pattern: Pattern to check.

        Returns:
            True if should be ignored.
        """
        return any(pattern in ignore for ignore in self.ignore_list)

    def _replace_matches(
        self,
        content: str,
        pattern: str,
        category: str,
        dictionary: AnonymizationDictionary,
    ) -> str:
        """Replace regex matches with anonymized placeholders.

        Args:
            content: The content to process.
            pattern: The regex pattern.
            category: The category name.
            dictionary: The anonymization dictionary.

        Returns:
            Content with matches replaced.
        """

        def replacer(match):  # type: ignore
            original = match.group(0)
            if self._should_ignore(original):
                return original
            return dictionary.add_mapping(original, category)

        return re.sub(pattern, replacer, content)

    def _redact_high_entropy(self, content: str) -> str:
        """Redact high-entropy strings that likely contain secrets.

        Args:
            content: The content to process.

        Returns:
            Content with high-entropy strings redacted.
        """
        # Pattern for AWS keys (AKIA...)
        content = re.sub(r"AKIA[0-9A-Z]{16}", "[AWS_ACCESS_KEY]", content)

        # Pattern for JWT-like tokens (base64 segments separated by dots)
        jwt_pattern = r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.?[A-Za-z0-9_-]*"
        content = re.sub(jwt_pattern, "[JWT_TOKEN]", content)

        # Pattern for Stripe API keys
        content = re.sub(r"sk_(?:live|test)_[A-Za-z0-9]{20,}", "[STRIPE_KEY]", content)

        # Pattern for SSH private keys
        content = re.sub(
            r"-----BEGIN (?:RSA|EC|OPENSSH) PRIVATE KEY-----",
            "[SSH_PRIVATE_KEY_START]",
            content,
        )
        content = re.sub(
            r"-----END (?:RSA|EC|OPENSSH) PRIVATE KEY-----",
            "[SSH_PRIVATE_KEY_END]",
            content,
        )

        return content

    @staticmethod
    def _calculate_entropy(value: str) -> float:
        """Calculate Shannon entropy of a string.

        Args:
            value: The string to analyze.

        Returns:
            Entropy value (bits per character).
        """
        import math

        if not value:
            return 0.0

        # Count character frequencies
        frequencies = {}
        for char in value:
            frequencies[char] = frequencies.get(char, 0) + 1

        # Calculate entropy
        entropy = 0.0
        for count in frequencies.values():
            probability = count / len(value)
            entropy -= probability * math.log2(probability)

        return entropy
