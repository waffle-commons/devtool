from dataclasses import dataclass
from typing import Iterator

import pytest

# Assuming the original code is saved in a module named 'processor_module'
# Since the provided code snippet is self-contained, I will define the classes here for testing scope.


@dataclass
class ReviewState:
    thinking: str = ""
    final: str = ""
    is_thinking_block: bool = False


class OllamaStreamProcessor:
    """Processes incoming stream chunks, parsing out <think> boundaries."""

    def __init__(self):
        self.state = ReviewState()

    def process(self, stream: Iterator[str]) -> Iterator[ReviewState]:
        """Consumes a raw string stream and emits updated structural ReviewState."""
        # Reset state just in case the processor object is reused in tests
        self.state = ReviewState()

        for chunk in stream:
            # Detect opening tags
            if "<think>" in chunk:
                self.state.is_thinking_block = True
                chunk = chunk.replace("<think>", "")

            # Detect closing tags
            if "</think>" in chunk:
                # This logic handles the split based on the content *after* initial tag cleanup
                parts = chunk.split("</think>")

                # The content before the first </think> goes into thinking
                # Since chunk already had <think> stripped, the content in parts[0] is the thinking content
                self.state.thinking += parts[0]

                # The content after the last </think> goes into final
                self.state.final += parts[1] if len(parts) > 1 else ""

                yield self.state
                continue

            # Accumulate buffer based on internal state
            if self.state.is_thinking_block:
                self.state.thinking += chunk
            else:
                self.state.final += chunk

            yield self.state


# --- Unit Tests ---


@pytest.fixture
def processor():
    """Fixture to provide a fresh instance of the processor for each test."""
    return OllamaStreamProcessor()


def test_empty_stream(processor: OllamaStreamProcessor):
    """Tests processing an empty stream."""
    # Arrange
    mock_stream = iter([])

    # Act
    results = list(processor.process(mock_stream))

    # Assert
    assert results == []


def test_happy_path_simple_transaction(processor: OllamaStreamProcessor):
    """Tests a clean flow: final content -> thinking -> final content."""
    # Arrange
    chunks = [
        "Initial text.",
        "This is the thought process.",
        "</think> Final summary.",
    ]
    mock_stream = iter(chunks)

    # Act
    results = list(processor.process(mock_stream))

    # Assert
    # 1. "Initial text." -> final
    assert results[0].final == "Initial text."
    # 2. "This is the thought process." -> thinking
    assert results[1].thinking == "This is the thought process."
    # 3. "</think> Final summary." -> ends thinking, updates final
    assert results[2].thinking == "This is the thought process."
    assert results[2].final == "Initial text.Final summary."
    assert results[2].is_thinking_block is False


def test_pre_thinking_content_and_transition(processor: OllamaStreamProcessor):
    """Tests content accumulation before any tags are encountered."""
    # Arrange
    chunks = [
        "The story begins. ",
        "<think>The internal monologue.",
        "</think> and then continues.",
    ]
    mock_stream = iter(chunks)

    # Act
    results = list(processor.process(mock_stream))

    # Assert
    # 1. "The story begins. " -> final
    assert results[0].final == "The story begins. "
    # 2. "<think>The internal monologue." -> state change, content accumulation
    assert results[1].thinking == "The internal monologue."
    # 3. "</think> and then continues." -> state change, update final
    assert results[2].thinking == "The internal monologue."
    assert results[2].final == "The story begins. and then continues."
    assert results[2].is_thinking_block is False


def test_single_chunk_with_full_block(processor: OllamaStreamProcessor):
    """Tests a scenario where the entire transaction happens in one chunk."""
    # Arrange
    chunks = ["START: This is the thought <think>content</think> END."]
    mock_stream = iter(chunks)

    # Act
    results = list(processor.process(mock_stream))

    # Assert
    # Note: The initial final content is "START: This is the thought ",
    # The thinking content is "content", and the final remainder is " END."
    assert len(results) == 1
    assert results[0].thinking == "content"
    assert results[0].final == "START: This is the thought  END."
    assert results[0].is_thinking_block is False


def test_multi_block_transition_and_accumulation(processor: OllamaStreamProcessor):
    """Tests multiple, consecutive think/final transitions."""
    # Arrange
    chunks = [
        "Context 1.",  # Final
        "<think>First thought chunk.",  # Start thinking
        "Second thought chunk.",  # Accumulating thought
        "</think> Context 2. ",  # End thinking, Final update
        "<think>Another thought.",  # Start thinking (overwriting old state)
        "The end.</think>",  # End thinking, Final update
    ]
    mock_stream = iter(chunks)

    # Act
    results = list(processor.process(mock_stream))

    # Assert (Expected 4 yielded states)
    assert len(results) == 4

    # State 1: Context 1.
    assert results[0].final == "Context 1."
    assert results[0].thinking == ""

    # State 2: Transition to thinking state
    assert results[1].thinking == "First thought chunk."
    assert results[1].final == "Context 1."  # Final content should not change here

    # State 3: End of first block. Final content accumulates.
    assert results[2].thinking == "First thought chunk.Second thought chunk."
    assert results[2].final == "Context 1.Context 2. "

    # State 4: End of second block. State accumulates.
    assert results[3].thinking == "Another thought.The end."
    assert results[3].final == "Context 1.Context 2. "


def test_edge_case_partial_tag_handling(processor: OllamaStreamProcessor):
    """Tests chunks that contain parts of tags but are correctly processed."""
    # Arrange
    # This stream simulates a messy chunk where the start/end tags might be fragmented
    chunks = [
        "Start of final text.",
        "<think>chunk1",  # Starts thinking, not fully formed tag
        "more text chunk2</think>",  # Should process content after </think> as final
        "Final text after block.",
    ]
    mock_stream = iter(chunks)

    # Act
    results = list(processor.process(mock_stream))

    # Assert
    # 1. Start of final text.
    assert results[0].final == "Start of final text."

    # 2. <think>chunk1 (State changes, accumulates)
    assert results[1].is_thinking_block is True
    assert results[1].thinking == "chunk1"

    # 3. more text chunk2</think> (Processes, updates final)
    assert results[2].is_thinking_block is False
    # Thinking content accumulated: "chunk1more text chunk2"
    assert results[2].thinking == "chunk1more text chunk2"
    # Final content accumulated: "Start of final text.more text chunk2" (Note: The 'more text' was treated as final
    # until the </think> was found, then it was reset/overwritten by the split logic relative to the parts array)
    # Based on the provided implementation:
    # parts = ['chunk1more text chunk2', '']
    # thinking += 'chunk1more text chunk2'
    # final += ''
    assert results[2].final == "Start of final text."

    # 4. Final text after block. (Accumulates in final)
    assert results[3].final == "Start of final text.Final text after block."
    assert results[3].thinking == "chunk1more text chunk2"


def test_thinking_block_is_not_affected_by_final_content(
    processor: OllamaStreamProcessor,
):
    """Ensures that when a block transitions, the state is correctly captured."""
    # Arrange
    chunks = [
        "Final text before block.",
        "<think>The thought.",
        "continuation.</think>",
        "Final text after block.",
    ]
    mock_stream = iter(chunks)

    # Act
    results = list(processor.process(mock_stream))

    # Assert
    assert len(results) == 3

    # State 1: Final content
    assert results[0].final == "Final text before block."

    # State 2: Accumulating thinking
    assert results[1].thinking == "The thought."

    # State 3: End of block
    assert results[2].thinking == "The thought.continuation."
    assert results[2].final == "Final text before block.Final text after block."
    assert results[2].is_thinking_block is False


def test_thinking_content_with_internal_tags(processor: OllamaStreamProcessor):
    """Tests that the processor handles tags within the thinking block itself."""
    # Arrange
    chunks = [
        "<think>This block contains an <think>error tag.</think> This is the actual thought.",
    ]
    mock_stream = iter(chunks)

    # Act
    results = list(processor.process(mock_stream))

    # Assert
    # The logic strips tags first, then accumulates.
    # First chunk:
    # 1. Detects <think>, state=True. Chunk becomes: "This block contains an <think>error tag.</think> This is the actual thought."
    # 2. Detects </think>. parts[0] = "This block contains an <think>error tag.". parts[1] = " This is the actual thought."
    # 3. State updates, yield.
    assert len(results) == 1
    assert results[0].thinking == "This block contains an <think>error tag."
    assert results[0].final == "This is the actual thought."
    assert results[0].is_thinking_block is False
