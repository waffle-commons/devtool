import typer
from rich.console import Console

app = typer.Typer(
    help="devtool - A privacy-first, local DevSecOps CLI tool", no_args_is_help=True
)
console = Console()


@app.callback()
def main():
    """
    devtool - local DevSecOps CLI
    """
    pass


from .commands.commit import commit_cmd  # noqa: E402

app.command("commit")(commit_cmd)

from .commands.debug_ollama import debug_ollama_cmd  # noqa: E402

app.command("debug-ollama")(debug_ollama_cmd)

from .commands.pre_review import pre_review_cmd  # noqa: E402

app.command("review")(pre_review_cmd)

from .commands.sec_audit import sec_audit_cmd  # noqa: E402

app.command("sec-audit")(sec_audit_cmd)

from .commands.docgen import docgen_cmd  # noqa: E402

app.command("docgen")(docgen_cmd)

from .commands.testgen import testgen_cmd  # noqa: E402

app.command("testgen")(testgen_cmd)

from .commands.repo_analysis import repo_analysis_cmd  # noqa: E402

app.command("repo-analysis")(repo_analysis_cmd)

from .commands.rag import ask_cmd, index_cmd  # noqa: E402

app.command("index")(index_cmd)
app.command("ask")(ask_cmd)

from .commands.anonymize import anonymize_cmd  # noqa: E402

app.command("anonymize")(anonymize_cmd)

from .commands.mock_data import mock_data_cmd  # noqa: E402

app.command("mock-data")(mock_data_cmd)
