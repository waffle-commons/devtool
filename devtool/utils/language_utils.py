"""Language detection and mapping utilities."""

from pathlib import Path

LANGUAGE_MAPPING: dict[str, dict[str, str]] = {
    ".py": {
        "language": "Python",
        "framework": "pytest",
        "prefix": "test_",
        "suffix": ".py",
    },
    ".php": {
        "language": "PHP",
        "framework": "phpunit",
        "prefix": "",
        "suffix": "Test.php",
    },
    ".cs": {"language": "C#", "framework": "xunit", "prefix": "", "suffix": "Tests.cs"},
    ".kt": {
        "language": "Kotlin",
        "framework": "junit",
        "prefix": "",
        "suffix": "Test.kt",
    },
    ".ts": {
        "language": "TypeScript",
        "framework": "jest",
        "prefix": "",
        "suffix": ".spec.ts",
    },
    ".js": {
        "language": "JavaScript",
        "framework": "jest",
        "prefix": "",
        "suffix": ".spec.js",
    },
}


def detect_language_from_dir(root: Path) -> str:
    """Return the dominant language in a directory by counting file extensions."""
    counts: dict[str, int] = {}
    for item in root.rglob("*"):
        if item.is_file() and item.suffix.lower() in LANGUAGE_MAPPING:
            lang = LANGUAGE_MAPPING[item.suffix.lower()]["language"]
            counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else "Generic"
