"""Tests for devtool.prompts — prompt template functions."""

from devtool.prompts import rag_ask_prompt


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
