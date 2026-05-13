"""Tests for AST-aware semantic chunking (ast_chunker module)."""

from pathlib import Path

from devtool.services.ast_chunker import _chunk_text, chunk_file


class TestFallbackChunking:
    """Test the naive character-based fallback chunker."""

    def test_fallback_returns_correct_structure(self) -> None:
        """Fallback chunks should have all required keys."""
        text = "x" * 2000
        chunks = _chunk_text(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert "text" in chunk
            assert "symbol_type" in chunk
            assert "symbol_name" in chunk
            assert "parent_class" in chunk
            assert chunk["symbol_type"] == "text"
            assert chunk["symbol_name"] == ""
            assert chunk["parent_class"] == ""

    def test_fallback_respects_chunk_size(self) -> None:
        """Fallback chunks should not exceed chunk_size."""
        text = "x" * 3000
        chunks = _chunk_text(text, chunk_size=1000, overlap=200)
        for chunk in chunks:
            assert (
                len(chunk["text"]) <= 1200
            )  # chunk_size + some tolerance for boundaries


class TestPythonChunking:
    """Test Python AST extraction."""

    def test_python_extracts_function(self) -> None:
        """Python .py file should extract function_definition nodes."""
        source = """
def hello_world():
    return 42

def another_func(x, y):
    return x + y
"""
        path = Path("test.py")
        chunks = chunk_file(path, source)

        # Should have at least 2 function chunks
        func_chunks = [c for c in chunks if c["symbol_type"] == "function_definition"]
        assert len(func_chunks) >= 2
        assert any("hello_world" in c["symbol_name"] for c in func_chunks)
        assert any("another_func" in c["symbol_name"] for c in func_chunks)

    def test_python_extracts_class(self) -> None:
        """Python .py file should extract class_definition nodes."""
        source = """
class MyClass:
    def __init__(self):
        self.value = 42
    
    def method(self):
        return self.value
"""
        path = Path("test.py")
        chunks = chunk_file(path, source)

        # Should have a class chunk and method chunks
        class_chunks = [c for c in chunks if c["symbol_type"] == "class_definition"]
        assert len(class_chunks) >= 1
        assert any("MyClass" in c["symbol_name"] for c in class_chunks)

        # Method should have parent_class set
        method_chunks = [
            c
            for c in chunks
            if c["symbol_type"] == "function_definition" and c["parent_class"]
        ]
        assert len(method_chunks) >= 1
        assert all(c["parent_class"] == "MyClass" for c in method_chunks)

    def test_python_top_level_assignment(self) -> None:
        """Python should extract top-level constants (expression_statement)."""
        source = """
MAX_RETRIES = 3
DEBUG = True

def func():
    pass
"""
        path = Path("test.py")
        chunks = chunk_file(path, source)

        # Should have assignment chunks (expression_statement)
        expr_chunks = [c for c in chunks if c["symbol_type"] == "expression_statement"]
        assert len(expr_chunks) >= 2

    def test_python_empty_file_returns_empty_list(self) -> None:
        """Empty Python file should return empty list."""
        path = Path("test.py")
        chunks = chunk_file(path, "")
        assert chunks == []

    def test_python_malformed_code_falls_back(self) -> None:
        """Malformed Python code should fall back to naive chunking without error."""
        source = "def incomplete( ["  # Intentionally broken syntax
        path = Path("test.py")
        chunks = chunk_file(path, source)

        # Should not raise; should fall back to naive chunks
        assert len(chunks) > 0
        assert chunks[0]["symbol_type"] == "text"


class TestPHPChunking:
    """Test PHP AST extraction."""

    def test_php_extracts_class_and_method(self) -> None:
        """PHP .php file should extract class and method nodes."""
        source = """<?php
class UserService {
    public function authenticate($user) {
        return true;
    }
    
    public function logout($user) {
        return true;
    }
}
"""
        path = Path("service.php")
        chunks = chunk_file(path, source)

        # Should have class chunk
        class_chunks = [c for c in chunks if c["symbol_type"] == "class_declaration"]
        assert len(class_chunks) >= 1
        assert any("UserService" in c["symbol_name"] for c in class_chunks)

        # Should have method chunks with parent_class
        method_chunks = [c for c in chunks if c["symbol_type"] == "method_declaration"]
        assert len(method_chunks) >= 2
        assert all(c["parent_class"] == "UserService" for c in method_chunks)

    def test_php_extracts_function(self) -> None:
        """PHP should extract top-level functions."""
        source = """<?php
function helper() {
    return 42;
}

class Foo {}
"""
        path = Path("helper.php")
        chunks = chunk_file(path, source)

        # Should have function_definition chunk
        func_chunks = [c for c in chunks if c["symbol_type"] == "function_definition"]
        assert len(func_chunks) >= 1
        assert any("helper" in c["symbol_name"] for c in func_chunks)

    def test_php_extracts_property(self) -> None:
        """PHP should extract property_declaration nodes."""
        source = """<?php
class Config {
    private string $name;
    public int $value;
}
"""
        path = Path("config.php")
        chunks = chunk_file(path, source)

        # Should have property chunks
        prop_chunks = [c for c in chunks if c["symbol_type"] == "property_declaration"]
        assert len(prop_chunks) >= 2


class TestCSharpChunking:
    """Test C# AST extraction."""

    def test_csharp_extracts_class_and_method(self) -> None:
        """C# .cs file should extract class and method nodes."""
        source = """
namespace MyApp {
    public class Calculator {
        public int Add(int a, int b) {
            return a + b;
        }
        
        public int Multiply(int a, int b) {
            return a * b;
        }
    }
}
"""
        path = Path("calculator.cs")
        chunks = chunk_file(path, source)

        # Should have class chunk
        class_chunks = [c for c in chunks if c["symbol_type"] == "class_declaration"]
        assert len(class_chunks) >= 1
        assert any("Calculator" in c["symbol_name"] for c in class_chunks)

        # Should have method chunks with parent_class
        method_chunks = [c for c in chunks if c["symbol_type"] == "method_declaration"]
        assert len(method_chunks) >= 2
        assert all(c["parent_class"] == "Calculator" for c in method_chunks)

    def test_csharp_extracts_property_and_field(self) -> None:
        """C# should extract property_declaration and field_declaration nodes."""
        source = """
public class Config {
    private int _value;
    public string Name { get; set; }
}
"""
        path = Path("config.cs")
        chunks = chunk_file(path, source)

        # Should have property and field chunks
        prop_chunks = [c for c in chunks if c["symbol_type"] == "property_declaration"]
        field_chunks = [c for c in chunks if c["symbol_type"] == "field_declaration"]
        assert len(prop_chunks) >= 1
        assert len(field_chunks) >= 1

    def test_csharp_extracts_constructor(self) -> None:
        """C# should extract constructor_declaration nodes."""
        source = """
public class MyClass {
    private int _value;
    
    public MyClass(int value) {
        _value = value;
    }
}
"""
        path = Path("myclass.cs")
        chunks = chunk_file(path, source)

        # Should have constructor chunk
        ctor_chunks = [
            c for c in chunks if c["symbol_type"] == "constructor_declaration"
        ]
        assert len(ctor_chunks) >= 1
        assert any("MyClass" in c["symbol_name"] for c in ctor_chunks)


class TestOversizedNodes:
    """Test handling of nodes larger than CHUNK_SIZE."""

    def test_oversized_function_splits(self) -> None:
        """Functions larger than CHUNK_SIZE should be sub-chunked."""
        # Create a large function
        func_body = "\n    ".join(f"x = {i}" for i in range(500))
        source = f"""
def large_function():
    {func_body}
"""
        path = Path("large.py")
        chunks = chunk_file(path, source)

        # Should have multiple chunks from the same function
        func_chunks = [c for c in chunks if c["symbol_type"] == "function_definition"]
        assert len(func_chunks) >= 2
        # All should share the same symbol_name
        assert all("large_function" in c["symbol_name"] for c in func_chunks)


class TestUnsupportedExtensions:
    """Test fallback for unsupported file types."""

    def test_unsupported_extension_falls_back(self) -> None:
        """Unsupported extensions (.go, .js, .rb, etc.) should fall back to naive chunking."""
        source = "some code" * 200

        for ext in [".go", ".js", ".rb", ".java", ".ts"]:
            path = Path(f"file{ext}")
            chunks = chunk_file(path, source)

            # All chunks should be "text" type with empty symbol info
            assert len(chunks) > 0
            for chunk in chunks:
                assert chunk["symbol_type"] == "text"
                assert chunk["symbol_name"] == ""
                assert chunk["parent_class"] == ""

    def test_markdown_falls_back(self) -> None:
        """Markdown files should fall back to naive chunking."""
        source = "# Header\n" * 200
        path = Path("readme.md")
        chunks = chunk_file(path, source)

        assert len(chunks) > 0
        assert all(c["symbol_type"] == "text" for c in chunks)


class TestMetadataStructure:
    """Test that all chunks have correct metadata structure."""

    def test_all_chunks_have_required_keys(self) -> None:
        """Every chunk should have text, symbol_type, symbol_name, parent_class."""
        sources = [
            (Path("test.py"), "def foo():\n    pass"),
            (Path("test.php"), "<?php\nclass A {}"),
            (Path("test.cs"), "class B {}"),
            (Path("test.go"), "func main() {}"),
        ]

        for path, source in sources:
            chunks = chunk_file(path, source)
            for chunk in chunks:
                assert isinstance(chunk, dict)
                assert "text" in chunk
                assert "symbol_type" in chunk
                assert "symbol_name" in chunk
                assert "parent_class" in chunk
                assert isinstance(chunk["text"], str)
                assert isinstance(chunk["symbol_type"], str)
                assert isinstance(chunk["symbol_name"], str)
                assert isinstance(chunk["parent_class"], str)
