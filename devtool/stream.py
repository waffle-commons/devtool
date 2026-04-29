from dataclasses import dataclass
from typing import Iterator


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
        for chunk in stream:
            # Detect opening tags
            if "<think>" in chunk:
                self.state.is_thinking_block = True
                chunk = chunk.replace("<think>", "")

            # Detect closing tags
            if "</think>" in chunk:
                self.state.is_thinking_block = False
                parts = chunk.split("</think>")
                self.state.thinking += parts[0]
                self.state.final += parts[1] if len(parts) > 1 else ""
                yield self.state
                continue

            # Accumulate buffer based on internal state
            if self.state.is_thinking_block:
                self.state.thinking += chunk
            else:
                self.state.final += chunk

            yield self.state
