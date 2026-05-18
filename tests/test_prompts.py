"""Tests for devtool.prompts — prompt template functions."""

from devtool.prompts import (
    commit_prompt,
    docgen_prompt,
    gen_test_prompt,
    identify_external_calls_prompt,
    pre_review_prompt,
    rag_ask_prompt,
    repo_architect_prompt,
    sec_audit_prompt,
    summarize_file_prompt,
)


class TestCommitPrompt:
    """Test suite for commit_prompt (RFC 001)."""

    def test_commit_prompt_returns_tuple(self) -> None:
        """Test that commit_prompt returns (system, user) tuple."""
        diff = "diff --git a/file.py b/file.py\n+def new_func(): pass"
        result = commit_prompt(diff)

        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_commit_prompt_includes_diff(self) -> None:
        """Test that the diff is included in the prompt."""
        diff = "diff --git a/file.py b/file.py\n+def new_func(): pass"
        system, user = commit_prompt(diff)

        assert diff in user

    def test_commit_prompt_system_message_is_not_empty(self) -> None:
        """Test that system prompt is meaningful."""
        diff = "test diff"
        system, user = commit_prompt(diff)

        assert len(system) > 10
        assert "commit" in system.lower() or "conventional" in system.lower()


class TestPreReviewPrompt:
    """Test suite for pre_review_prompt (RFC 002)."""

    def test_pre_review_prompt_returns_tuple(self) -> None:
        """Test that pre_review_prompt returns (system, user) tuple."""
        diff = "diff --git a/file.py b/file.py\n-old code\n+new code"
        result = pre_review_prompt(diff=diff)

        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_pre_review_prompt_includes_diff(self) -> None:
        """Test that the diff is included in the prompt."""
        diff = "diff --git a/file.py b/file.py\n-old code\n+new code"
        system, user = pre_review_prompt(diff=diff)

        assert diff in user

    def test_pre_review_prompt_mentions_fixes(self) -> None:
        """Test that fix_mode enables patch format in the prompt."""
        diff = "diff --git a/file.py b/file.py\n-old code\n+new code"
        system, user = pre_review_prompt(diff=diff, fix_mode=True)

        # In fix_mode, the system/user prompt should mention patches/SEARCH/REPLACE
        # The prompt should guide the model to use SEARCH/REPLACE or similar format
        assert "fix" in (system + user).lower() or "patch" in (system + user).lower()


class TestSecAuditPrompt:
    """Test suite for sec_audit_prompt (RFC 004)."""

    def test_sec_audit_prompt_returns_tuple(self) -> None:
        """Test that sec_audit_prompt returns (system, user) tuple."""
        code = "import os\nos.system('rm -rf /')"
        result = sec_audit_prompt(code=code)

        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_sec_audit_prompt_includes_code(self) -> None:
        """Test that the code is included in the prompt."""
        code = "dangerous_code_here()"
        system, user = sec_audit_prompt(code=code)

        assert code in user

    def test_sec_audit_prompt_mentions_security(self) -> None:
        """Test that security is emphasized in the prompt."""
        code = "def example(): pass"
        system, user = sec_audit_prompt(code=code)

        assert (
            "security" in system.lower()
            or "vulnerability" in system.lower()
            or "audit" in system.lower()
        )


class TestIdentifyExternalCallsPrompt:
    """Test suite for identify_external_calls_prompt."""

    def test_identify_external_calls_returns_tuple(self) -> None:
        """Test that identify_external_calls_prompt returns (system, user) tuple."""
        code = "import requests\nresponse = requests.get('http://example.com')"
        result = identify_external_calls_prompt(code=code)

        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_identify_external_calls_includes_code(self) -> None:
        """Test that the code is included in the prompt."""
        code = "external_api.call()"
        system, user = identify_external_calls_prompt(code=code)

        assert code in user


class TestDocgenPrompt:
    """Test suite for docgen_prompt (RFC 005)."""

    def test_docgen_prompt_returns_tuple(self) -> None:
        """Test that docgen_prompt returns (system, user) tuple."""
        result = docgen_prompt(
            source_code="def example(): pass",
            doc_type="tutorial",
            language="python",
            context_hint="Example module",
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_docgen_prompt_includes_source_code(self) -> None:
        """Test that source code is included in the prompt."""
        source_code = "def calculate(x, y):\n    return x + y"
        system, user = docgen_prompt(
            source_code=source_code,
            doc_type="tutorial",
            language="python",
        )

        assert source_code in user

    def test_docgen_prompt_mentions_doc_type(self) -> None:
        """Test that the documentation type is mentioned."""
        system, user = docgen_prompt(
            source_code="def example(): pass",
            doc_type="howto",
            language="python",
        )

        # Should mention the doc type or Diataxis in either system or user
        prompt_text = (system + user).lower()
        assert "how" in prompt_text or "diataxis" in prompt_text

    def test_docgen_prompt_mentions_language(self) -> None:
        """Test that the programming language is mentioned."""
        system, user = docgen_prompt(
            source_code="def example(): pass",
            doc_type="reference",
            language="python",
        )

        assert "python" in user.lower() or "python" in system.lower()


class TestTestgenPrompt:
    """Test suite for gen_test_prompt (RFC 003)."""

    def test_gen_test_prompt_returns_tuple(self) -> None:
        """Test that gen_test_prompt returns (system, user) tuple."""
        code = "def add(a, b):\n    return a + b"
        result = gen_test_prompt(
            source_code=code,
            language="python",
            framework="pytest",
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_gen_test_prompt_includes_source_code(self) -> None:
        """Test that source code is included in the prompt."""
        code = "def multiply(a, b): return a * b"
        system, user = gen_test_prompt(
            source_code=code,
            language="python",
            framework="pytest",
        )

        assert code in user

    def test_gen_test_prompt_mentions_framework(self) -> None:
        """Test that test framework is mentioned in prompt."""
        system, user = gen_test_prompt(
            source_code="def test(): pass",
            language="python",
            framework="unittest",
        )

        assert "unittest" in user.lower() or "test" in system.lower()


class TestSummarizeFilePrompt:
    """Test suite for summarize_file_prompt."""

    def test_summarize_file_prompt_returns_tuple(self) -> None:
        """Test that summarize_file_prompt returns (system, user) tuple."""
        content = "def complex_function():\n    pass"
        result = summarize_file_prompt(content=content)

        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_summarize_file_prompt_includes_content(self) -> None:
        """Test that file content is included in the prompt."""
        content = "File content to summarize"
        system, user = summarize_file_prompt(content=content)

        assert content in user


class TestRepoArchitectPrompt:
    """Test suite for repo_architect_prompt (RFC 006)."""

    def test_repo_architect_prompt_returns_tuple(self) -> None:
        """Test that repo_architect_prompt returns (system, user) tuple."""
        tree = "src/\n  main.py\n  utils.py"
        summaries = "main: Entry point\nutils: Helper functions"
        result = repo_architect_prompt(tree=tree, summaries=summaries)

        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_repo_architect_prompt_includes_tree(self) -> None:
        """Test that directory tree is included in the prompt."""
        tree = "src/main.py"
        summaries = "test"
        system, user = repo_architect_prompt(tree=tree, summaries=summaries)

        assert tree in user

    def test_repo_architect_prompt_includes_summaries(self) -> None:
        """Test that file summaries are included in the prompt."""
        tree = "test"
        summaries = "main: Core logic"
        system, user = repo_architect_prompt(tree=tree, summaries=summaries)

        assert summaries in user


class TestRAGAskPrompt:
    """Test suite for rag_ask_prompt (RFC 016: Karpathy-style prompts)."""

    def test_rag_ask_prompt_karpathy_format(self) -> None:
        """Test: rag_ask_prompt output follows Karpathy-style format (RFC 016)."""
        question = "How does the auth module work?"
        context_block = (
            "[File: auth.py | Similarity: 0.8543 | Lines: 10-25]\n"
            "def login(username, password):\n"
            "    return validate_credentials(username, password)"
        )

        system, user_message = rag_ask_prompt(question, context_block)

        # System prompt should emphasize strict context grounding
        assert "code analysis expert" in system.lower()
        assert "ONLY the provided code context" in system
        assert "do not use external knowledge" in system.lower()

        # User message should have clear markers for context and question
        assert "[RETRIEVED CODE CONTEXT]" in user_message
        assert context_block in user_message
        assert "[QUESTION]" in user_message
        assert question in user_message

    def test_rag_ask_prompt_strict_instructions(self) -> None:
        """Test: system prompt emphasizes strict limitations."""
        question = "test"
        context_block = "test"

        system, _ = rag_ask_prompt(question, context_block)

        # Should explicitly say not to use external knowledge
        assert "explicitly" in system.lower() or "do not" in system.lower()
        assert "not found in the context" in system or "not in" in system.lower()

    def test_rag_ask_prompt_preserves_context_and_question(self) -> None:
        """Test: context and question are clearly separated."""
        question = "What is the database schema?"
        context_block = "Schema definition...\nTable users..."

        system, user_message = rag_ask_prompt(question, context_block)

        # Both context and question should be in the output
        assert context_block in user_message
        assert question in user_message

        # They should be clearly separated
        assert "[RETRIEVED CODE CONTEXT]" in user_message
        assert "[QUESTION]" in user_message
