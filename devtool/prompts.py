"""Prompt templates for all devtool commands.

Single Responsibility: this module owns ALL prompt engineering.
The Ollama client (infrastructure) and commands (controllers) remain clean.

Each function returns a (system_prompt, user_prompt) tuple ready for the LLM.
"""

from typing import Optional


# ── Fix-mode suffix (RFC 011) ────────────────────────────────────────────────

_FIX_MODE_SUFFIX = (
    "\n\nIMPORTANT — AUTO-FIX MODE: In addition to your review, for every issue you identify "
    "that can be fixed programmatically, output a structured patch block using EXACTLY this format:\n\n"
    "<<<< SEARCH file:path/to/file.py\n"
    "original code that needs to change (copy it EXACTLY)\n"
    "==== REPLACE\n"
    "the corrected code\n"
    ">>>>\n\n"
    "You may output multiple patch blocks. The file path MUST be relative to the project root. "
    "The SEARCH section must match the existing code EXACTLY (including whitespace). "
    "Place all patch blocks AFTER your review commentary."
)


# ── RAG context suffixes ─────────────────────────────────────────────────────

_RAG_REVIEW_SUFFIX = (
    "\n\nYou are also provided with [REPOSITORY CONTEXT] containing related classes, "
    "interfaces, and modules from the same codebase. Use this context to understand "
    "the broader architecture and detect violations that span across files — such as "
    "broken contracts, misused abstractions, or coupling issues invisible from the diff alone."
)

_RAG_SECURITY_SUFFIX = (
    "\n\nYou are also provided with [CROSS-FILE CONTEXT] showing how the audited code "
    "is used elsewhere in the repository. Use this to detect source-to-sink vulnerabilities "
    "where a seemingly safe function receives unvalidated user input from a caller in another file."
)

_RAG_TESTGEN_SUFFIX = (
    "\n\nYou are also provided with [ADDITIONAL REPOSITORY CONTEXT] containing "
    "related interfaces, traits, dependencies, and helper classes from the same codebase. "
    "Use this context to accurately mock dependencies, type-hint parameters, and understand "
    "the contracts that the code under test relies on."
)


# ── Commit ───────────────────────────────────────────────────────────────────


def commit_prompt(diff: str) -> tuple[str, str]:
    """Return (system, user) prompts for commit message generation."""
    system = (
        "You are an expert developer. Read the following `git diff` and write a single "
        "commit message following the Conventional Commits specification. Use present tense. "
        "Do not add any markdown formatting, explanations, or extra text. Only output the commit message."
    )
    return system, diff


# ── Pre-Review ───────────────────────────────────────────────────────────────


def pre_review_prompt(
    diff: str,
    rag_context: Optional[str] = None,
    fix_mode: bool = False,
) -> tuple[str, str]:
    """Return (system, user) prompts for code review."""
    system = (
        "You are a strict Senior Developer specializing in PHP and C#. "
        "Review the following git diff. Identify SOLID principle violations, "
        "high cyclomatic complexity, and code smells. Provide your feedback in a "
        "structured Markdown format with actionable refactoring suggestions. "
        "Be concise and prioritize maintainability."
    )
    prompt_body = diff

    if rag_context:
        system += _RAG_REVIEW_SUFFIX
        prompt_body += f"\n\n[REPOSITORY CONTEXT]\n{rag_context}"

    if fix_mode:
        system += _FIX_MODE_SUFFIX

    return system, prompt_body


# ── Security Audit ───────────────────────────────────────────────────────────


def sec_audit_prompt(
    code: str,
    rag_context: Optional[str] = None,
    fix_mode: bool = False,
) -> tuple[str, str]:
    """Return (system, user) prompts for OWASP security audit."""
    system = (
        "You are a strict DevSecOps Security Auditor specializing in PHP, C#, and general web development. "
        "Analyze the provided code for security vulnerabilities. "
        "Focus heavily on the OWASP Top 10: SQL Injection, Cross-Site Scripting (XSS), "
        "Insecure Direct Object References (IDOR), hardcoded secrets/passwords, and unsafe deserialization. "
        "IMPORTANT: Completely ignore any line of code that has the comment "
        "`// devtool-ignore-sec` or `# devtool-ignore-sec` appended to it. "
        "If vulnerabilities are found, format EVERY finding strictly as: "
        "[Severity (Critical/High/Medium/Low)] - [File/Line] - [Description] - [Remediation]. "
        "Output one finding per line. Do not add any prose or markdown headers. "
        "CRITICAL INSTRUCTION: If absolutely no vulnerabilities are found, "
        "your entire output MUST be exactly the string NO_VULNERABILITIES_FOUND and nothing else."
    )
    prompt_body = code

    if fix_mode:
        system += _FIX_MODE_SUFFIX

    if rag_context:
        system += _RAG_SECURITY_SUFFIX
        prompt_body += f"\n\n[CROSS-FILE CONTEXT]\n{rag_context}"

    return system, prompt_body


# ── Diataxis Documentation ───────────────────────────────────────────────────

_DIATAXIS_PROMPTS: dict[str, str] = {
    "tutorial": (
        "You are a technical writer using the Diátaxis documentation framework. "
        "Create a 'Tutorial' document for the provided {language} source code. "
        "Focus on LEARNING by DOING. Guide the reader step-by-step through a practical implementation. "
        "Do not explain deep theory — keep it action-oriented and beginner-friendly. "
        "Output strict, clean Markdown compatible with Obsidian and MkDocs. "
        "Use ## headings, fenced code blocks with language tags, and clear numbered steps."
    ),
    "howto": (
        "You are a technical writer using the Diátaxis documentation framework. "
        "Create a 'How-to Guide' for the provided {language} source code. "
        "Focus on achieving a SPECIFIC GOAL. Provide practical, problem-solving steps. "
        "Assume the reader already understands the domain basics. "
        "Output strict, clean Markdown compatible with Obsidian and MkDocs. "
        "Use ## headings, fenced code blocks with language tags, and concise numbered steps."
    ),
    "reference": (
        "You are a technical writer using the Diátaxis documentation framework. "
        "Create a 'Reference' document for the provided {language} source code. "
        "Focus on INFORMATION. Document every public class, method, parameter, return type, "
        "and exception in a structured, austere, and accurate format. "
        "Use tables where appropriate. Output strict, clean Markdown compatible with Obsidian and MkDocs."
    ),
    "explanation": (
        "You are a technical writer using the Diátaxis documentation framework. "
        "Create an 'Explanation' document for the provided {language} source code. "
        "Focus on UNDERSTANDING. Discuss the architectural choices, underlying concepts, "
        "design patterns, and the reasoning behind key decisions. "
        "Do not focus on step-by-step instructions. "
        "Output strict, clean Markdown compatible with Obsidian and MkDocs. "
        "Use ## headings and narrative prose."
    ),
}


def docgen_prompt(
    source_code: str,
    doc_type: str,
    language: str,
    context_hint: str = "",
    existing_doc: Optional[str] = None,
) -> tuple[str, str]:
    """Return (system, user) prompts for Diataxis documentation generation."""
    base_prompt = _DIATAXIS_PROMPTS.get(doc_type, _DIATAXIS_PROMPTS["reference"])
    system = base_prompt.format(language=language)

    if existing_doc:
        system += (
            "\n\nIMPORTANT: An existing documentation file is provided below (marked [EXISTING DOC]). "
            "Your task is to UPDATE it: integrate new content, update outdated sections, "
            "and preserve any manually written sections that are still accurate. "
            "Output the COMPLETE updated document — do not truncate."
        )
        prompt_body = (
            f"[SOURCE CODE]\n{source_code}"
            + (f"\n\n[ADDITIONAL CONTEXT]\n{context_hint}" if context_hint else "")
            + f"\n\n[EXISTING DOC]\n{existing_doc}"
        )
    else:
        prompt_body = f"[SOURCE CODE]\n{source_code}" + (
            f"\n\n[ADDITIONAL CONTEXT]\n{context_hint}" if context_hint else ""
        )

    return system, prompt_body


# ── Test Generation ──────────────────────────────────────────────────────────


def testgen_prompt(
    source_code: str,
    language: str,
    framework: str,
    existing_test_content: Optional[str] = None,
    rag_context: Optional[str] = None,
) -> tuple[str, str]:
    """Return (system, user) prompts for unit test generation."""
    if existing_test_content:
        system = (
            f"You are an expert SDET (Software Development Engineer in Test). "
            f"You will be provided with {language} source code and its existing {framework} unit test file. "
            "Your task is to update the existing test file. Add new tests for any uncovered methods or edge cases, "
            "and modify existing tests if the source signatures have changed. "
            "CRITICAL: Do NOT remove or delete existing valid tests. Output ONLY the entire updated test file code, "
            "no markdown wrappers unless requested."
        )
        prompt_body = f"Framework: {framework}\n\n[SOURCE CODE]\n{source_code}\n\n[EXISTING TEST CODE]\n{existing_test_content}"
    else:
        system = (
            f"You are an expert SDET (Software Development Engineer in Test). "
            f"Write unit tests for the following {language} code using the {framework} framework. "
            "Identify edge cases, null checks, and happy paths. "
            "Structure every test strictly using the Arrange, Act, Assert (AAA) pattern. "
            "Output ONLY the test file code, no markdown wrappers unless requested."
        )
        prompt_body = f"Framework: {framework}\n\n[SOURCE CODE]\n{source_code}"

    if rag_context:
        system += _RAG_TESTGEN_SUFFIX
        prompt_body += f"\n\n[ADDITIONAL REPOSITORY CONTEXT]\n{rag_context}"

    return system, prompt_body


# ── Repository Analysis ──────────────────────────────────────────────────────


def summarize_file_prompt(content: str) -> tuple[str, str]:
    """Return (system, user) prompts for file summarization (Map phase)."""
    system = (
        "Summarize the purpose, main components, and obvious technical debt of this code in 3 bullet points. "
        "Keep it extremely brief."
    )
    return system, content


def repo_architect_prompt(tree: str, summaries: str) -> tuple[str, str]:
    """Return (system, user) prompts for architecture report (Reduce phase)."""
    system = (
        "You are a Lead Software Architect. Based on the provided file tree and summaries, "
        "conduct a complete audit of the repository. Identify systemic architectural flaws, "
        "SOLID violations, and technical debt. Output a comprehensive Markdown report including "
        "an 'Architecture Overview' and a 'Prioritized Action Plan'."
    )
    prompt_body = f"[DIRECTORY STRUCTURE]\n{tree}\n\n[FILE SUMMARIES]\n{summaries}"
    return system, prompt_body


# ── RAG Ask ──────────────────────────────────────────────────────────────────


def rag_ask_prompt(question: str, context_block: str) -> tuple[str, str]:
    """Return (system, user) prompts for RAG-powered Q&A."""
    system = (
        "You are a senior software engineer answering questions about a codebase. "
        "Use ONLY the provided code context to answer. If the context is insufficient, say so. "
        "Be concise and reference file paths when relevant."
    )
    prompt_body = (
        f"[RETRIEVED CODE CONTEXT]\n{context_block}\n\n"
        f"[QUESTION]\n{question}"
    )
    return system, prompt_body
