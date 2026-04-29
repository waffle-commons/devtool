"""Tests for devtool.stream — OllamaStreamProcessor and ReviewState."""

import pytest

from devtool.stream import OllamaStreamProcessor, ReviewState


class TestReviewState:
    def test_defaults(self):
        s = ReviewState()
        assert s.thinking == ""
        assert s.final == ""
        assert s.is_thinking_block is False


class TestStreamProcessor:
    def test_plain_text(self):
        proc = OllamaStreamProcessor()
        chunks = ["Hello ", "World"]
        states = list(proc.process(iter(chunks)))
        assert states[-1].final == "Hello World"
        assert states[-1].thinking == ""

    def test_think_block_extraction(self):
        proc = OllamaStreamProcessor()
        chunks = ["<think>", "reasoning here", "</think>", "final answer"]
        states = list(proc.process(iter(chunks)))
        last = states[-1]
        assert "reasoning here" in last.thinking
        assert "final answer" in last.final
        assert last.is_thinking_block is False

    def test_think_inline_open_and_close(self):
        proc = OllamaStreamProcessor()
        chunks = ["<think>I am thinking</think>done"]
        states = list(proc.process(iter(chunks)))
        last = states[-1]
        assert "I am thinking" in last.thinking
        assert "done" in last.final

    def test_no_think_tags(self):
        proc = OllamaStreamProcessor()
        chunks = ["just ", "text"]
        states = list(proc.process(iter(chunks)))
        assert states[-1].final == "just text"
        assert states[-1].thinking == ""

    def test_empty_stream(self):
        proc = OllamaStreamProcessor()
        states = list(proc.process(iter([])))
        assert states == []

    def test_multiple_think_blocks(self):
        proc = OllamaStreamProcessor()
        chunks = ["<think>first</think>answer1 ", "<think>second</think>answer2"]
        states = list(proc.process(iter(chunks)))
        last = states[-1]
        assert "first" in last.thinking
        assert "second" in last.thinking
        assert "answer1" in last.final
        assert "answer2" in last.final
