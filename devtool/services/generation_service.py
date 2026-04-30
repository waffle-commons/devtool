"""Generation service — composes prompts with the LLM transport layer.

This service replaces the domain-level functions that previously lived in
ollama_client.py (SRP violation). It orchestrates:
  1. Prompt construction (via prompts module)
  2. LLM invocation (via ILanguageModel interface)

Commands call this service through the DI container — never importing
ollama_client directly for domain tasks.
"""

from typing import Iterator, Optional

from ..interfaces import ILanguageModel
from ..prompts import (
    commit_prompt,
    docgen_prompt,
    pre_review_prompt,
    rag_ask_prompt,
    repo_architect_prompt,
    sec_audit_prompt,
    summarize_file_prompt,
    testgen_prompt,
)


class GenerationService:
    """Orchestrates prompt building and LLM invocation for all devtool commands.

    Each method accepts domain inputs, builds the appropriate prompt, and
    delegates to the injected ILanguageModel. This keeps prompt logic in
    prompts.py, transport logic in ollama_client.py, and orchestration here.
    """

    def __init__(
        self,
        *,
        fast_model: ILanguageModel,
        coding_model: ILanguageModel,
        review_model: ILanguageModel,
        default_model: ILanguageModel,
    ):
        self._fast = fast_model
        self._coding = coding_model
        self._review = review_model
        self._default = default_model

    # ── Commit ───────────────────────────────────────────────────────────

    def generate_commit_message(self, diff: str) -> Optional[str]:
        """Generate a Conventional Commits message from a staged diff."""
        system, user = commit_prompt(diff)
        return self._fast.generate(user, system)

    # ── Pre-Review ───────────────────────────────────────────────────────

    def pre_review_stream(
        self,
        diff: str,
        rag_context: Optional[str] = None,
        fix_mode: bool = False,
    ) -> Iterator[str]:
        """Stream a code review analysis."""
        system, user = pre_review_prompt(diff, rag_context=rag_context, fix_mode=fix_mode)
        yield from self._review.stream(user, system)

    # ── Security Audit ───────────────────────────────────────────────────

    def sec_audit_stream(
        self,
        code: str,
        rag_context: Optional[str] = None,
        fix_mode: bool = False,
    ) -> Iterator[str]:
        """Stream an OWASP-focused security audit."""
        system, user = sec_audit_prompt(code, rag_context=rag_context, fix_mode=fix_mode)
        yield from self._review.stream(user, system)

    # ── Documentation Generation ─────────────────────────────────────────

    def docgen_stream(
        self,
        source_code: str,
        doc_type: str,
        language: str,
        context_hint: str = "",
        existing_doc: Optional[str] = None,
    ) -> Iterator[str]:
        """Stream Diataxis documentation generation."""
        system, user = docgen_prompt(
            source_code, doc_type, language,
            context_hint=context_hint, existing_doc=existing_doc,
        )
        yield from self._coding.stream(user, system)

    # ── Test Generation ──────────────────────────────────────────────────

    def testgen_stream(
        self,
        source_code: str,
        language: str,
        framework: str,
        existing_test_content: Optional[str] = None,
        rag_context: Optional[str] = None,
    ) -> Iterator[str]:
        """Stream unit test generation."""
        system, user = testgen_prompt(
            source_code, language, framework,
            existing_test_content=existing_test_content,
            rag_context=rag_context,
        )
        yield from self._coding.stream(user, system)

    # ── Repository Analysis ──────────────────────────────────────────────

    def summarize_file(self, content: str) -> Optional[str]:
        """Summarize a single file (Map phase of repo-analysis)."""
        system, user = summarize_file_prompt(content)
        return self._fast.generate(user, system)

    def repo_architect_stream(self, tree: str, summaries: str) -> Iterator[str]:
        """Stream the architecture report (Reduce phase)."""
        system, user = repo_architect_prompt(tree, summaries)
        yield from self._default.stream(user, system)

    # ── RAG Ask ──────────────────────────────────────────────────────────

    def rag_ask_stream(self, question: str, context_block: str) -> Iterator[str]:
        """Stream a RAG-powered answer."""
        system, user = rag_ask_prompt(question, context_block)
        yield from self._default.stream(user, system)
