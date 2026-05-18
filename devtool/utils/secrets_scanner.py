"""High-entropy secrets scanner for detecting exposed credentials.

RFC 014: High-Entropy Secrets Scanner (Pre-LLM)
"""

import math
import re
from typing import NamedTuple

from rich.console import Console

console = Console()


class SecretMatch(NamedTuple):
    """Represents a detected secret match."""

    pattern_name: str
    value: str
    line_number: int
    column: int


class SecretsScanner:
    """Scans code for high-entropy secrets and known credential patterns."""

    # Known patterns for common secrets
    PATTERNS = {
        "aws_key": r"AKIA[0-9A-Z]{16}",
        "aws_secret": r"aws_secret_access_key\s*=\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?",
        "stripe_key": r"sk_(?:live|test)_[A-Za-z0-9]{20,}",
        "github_token": r"ghp_[A-Za-z0-9_]{36,255}",
        "jwt_token": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.?[A-Za-z0-9_-]*",
        "ssh_key": r"-----BEGIN (?:RSA|EC|OPENSSH|PRIVATE) KEY-----",
        "api_key": r"api[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9]{32,}['\"]?",
        "slack_token": r"xox[baprs]-[0-9]{12}-[0-9]{12}-[A-Za-z0-9]{32}",
        "docker_config": r"\"auth\":\s*\"[A-Za-z0-9+/=]{20,}\"",
        "password": r"password\s*[=:]\s*['\"]?[A-Za-z0-9!@#$%^&*]{12,}['\"]?",
    }

    def __init__(self) -> None:
        """Initialize the secrets scanner."""
        self.ignore_patterns = self._load_ignore_patterns()

    def _load_ignore_patterns(self) -> list[str]:
        """Load patterns to ignore from .devtool-ignore-secrets.

        Returns:
            List of patterns to skip during scanning.
        """
        from pathlib import Path

        ignore_file = Path.cwd() / ".devtool-ignore-secrets"
        if not ignore_file.exists():
            return []

        return [
            line.strip()
            for line in ignore_file.read_text().splitlines()
            if line.strip()
        ]

    def scan(self, content: str) -> list[SecretMatch]:
        """Scan content for secrets.

        Args:
            content: The code/text to scan.

        Returns:
            List of detected secrets.
        """
        matches: list[SecretMatch] = []

        for line_num, line in enumerate(content.splitlines(), 1):
            # Check against known patterns
            for pattern_name, pattern in self.PATTERNS.items():
                for regex_match in re.finditer(pattern, line, re.IGNORECASE):
                    if not self._is_ignored(regex_match.group(0)):
                        matches.append(
                            SecretMatch(
                                pattern_name=pattern_name,
                                value=regex_match.group(0)[:50],  # Truncate for display
                                line_number=line_num,
                                column=regex_match.start(),
                            )
                        )

            # Check for high-entropy strings
            entropy_matches = self._find_high_entropy_strings(line, line_num)
            matches.extend(entropy_matches)

        return matches

    def _is_ignored(self, value: str) -> bool:
        """Check if value matches any ignore pattern.

        Args:
            value: The value to check.

        Returns:
            True if should be ignored.
        """
        return any(re.search(pattern, value) for pattern in self.ignore_patterns)

    def _find_high_entropy_strings(self, line: str, line_num: int) -> list[SecretMatch]:
        """Find high-entropy strings that likely contain secrets.

        Args:
            line: The line to check.
            line_num: The line number.

        Returns:
            List of high-entropy matches.
        """
        matches: list[SecretMatch] = []

        # Look for quoted or assigned values
        pattern = r'["\']([A-Za-z0-9+/=_-]{32,})["\']'
        for match in re.finditer(pattern, line):
            value = match.group(1)
            entropy = self._calculate_entropy(value)
            # Threshold: 4.5 bits per character suggests randomness
            if entropy > 4.5 and not self._is_ignored(value):
                matches.append(
                    SecretMatch(
                        pattern_name="high_entropy",
                        value=value[:50],
                        line_number=line_num,
                        column=match.start(),
                    )
                )

        return matches

    @staticmethod
    def _calculate_entropy(value: str) -> float:
        """Calculate Shannon entropy of a string.

        Args:
            value: The string to analyze.

        Returns:
            Entropy value (bits per character).
        """
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
