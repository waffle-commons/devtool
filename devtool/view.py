from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from .config import Config
from .stream import ReviewState


class ReviewRenderer:
    """Manages the UI presentation layer for code reviews."""

    def __init__(self, config: Config, console: Console):
        self.config = config
        self.console = console

    def _generate_ui(self, state: ReviewState):
        """Constructs Rich elements dynamically based on state."""
        elements = []
        if state.thinking and self.config.show_thoughts:
            think_text = Text(state.thinking, style="dim cyan italic")
            elements.append(
                Panel(
                    think_text,
                    title="[dim cyan]AI Thinking Process[/dim cyan]",
                    border_style="dim cyan",
                )
            )

        if state.final:
            elements.append(Markdown(state.final))

        if not elements:
            return Text("Waiting for response...", style="dim")

        return Group(*elements)

    def render_live_stream(self, state_generator):
        """Consume state transitions and render to terminal using Live context."""
        final_state = ReviewState()
        with Live(
            self._generate_ui(final_state), console=self.console, refresh_per_second=10
        ) as live:
            for state in state_generator:
                live.update(self._generate_ui(state))
                final_state = state
        return final_state
