"""AST-based ingestion for the Project Memory layer.
Parses Python files, extracts modules, classes, functions/methods and their
relationships, and returns a list of :class:`~omem.codebase.types.CodeSymbol`.
"""

import ast
import os
from typing import List

from .types import CodeSymbol, SymbolType
from .utils import default_ignore_dirs, file_to_module, hash_text, is_python_file


class _ASTVisitor(ast.NodeVisitor):
    """Collects symbols from a single module.

    The visitor maintains a stack of the current namespace (module → class → …)
    and creates a :class:`CodeSymbol` for each class, function, and method.
    """

    def __init__(self, module_name: str, file_path: str, source: str):
        self.module_name = module_name
        self.file_path = file_path
        self.source = source
        self.lines = source.splitlines()
        self.symbols: List[CodeSymbol] = []
        # namespace stack always contains the module name first
        self.ns_stack: List[str] = [module_name]

    def _signature(self, node: ast.AST) -> str:
        """Return the exact source line that defines *node* (function or class)."""
        start = getattr(node, "lineno", 1) - 1
        if 0 <= start < len(self.lines):
            return self.lines[start].strip()
        return ""

    def _hash_code(self, node: ast.AST) -> str:
        """Hash the source code for *node* (including its body)."""
        try:
            src = ast.get_source_segment(self.source, node) or ""
        except Exception:
            src = ""
        return hash_text(src)

    def visit_ClassDef(self, node: ast.ClassDef):
        class_name = node.name
        symbol_id = f"{self.ns_stack[-1]}.{class_name}" if self.ns_stack else class_name
        doc = ast.get_docstring(node)
        signature = self._signature(node)
        content_hash = self._hash_code(node)
        # inheritance list
        bases = [self._resolve_name(b) for b in node.bases]
        # dependencies placeholder – will be filled later by a separate pass
        sym = CodeSymbol(
            symbol_id=symbol_id,
            symbol_type=SymbolType.CLASS,
            file_path=self.file_path,
            name=class_name,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            parent_id=self.ns_stack[-1] if self.ns_stack else None,
            docstring=doc,
            signature=signature,
            content_hash=content_hash,
            dependencies=bases,
        )
        self.symbols.append(sym)
        # descend into class body
        self.ns_stack.append(class_name)
        self.generic_visit(node)
        self.ns_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node, is_async=False)
        # do not descend into inner functions – they are not top‑level symbols

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node, is_async=True)
        # same handling as regular functions

    def _handle_function(self, node: ast.AST, is_async: bool):
        func_name = node.name
        # Determine if this is a method (inside a class) or a free function
        is_method = len(self.ns_stack) > 1  # first element is the module
        parent = self.ns_stack[-1] if self.ns_stack else self.module_name
        symbol_id = f"{parent}.{func_name}" if is_method else f"{self.module_name}.{func_name}"
        sym_type = SymbolType.METHOD if is_method else SymbolType.FUNCTION
        doc = ast.get_docstring(node)
        signature = self._signature(node)
        content_hash = self._hash_code(node)
        # simple dependency extraction: collect names of called functions (top‑level only)
        deps: List[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                deps.append(child.func.id)
        sym = CodeSymbol(
            symbol_id=symbol_id,
            symbol_type=sym_type,
            file_path=self.file_path,
            name=func_name,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            parent_id=parent if is_method else self.module_name,
            docstring=doc,
            signature=signature,
            content_hash=content_hash,
            dependencies=deps,
        )
        self.symbols.append(sym)
        # we do not descend further – nested functions are ignored for now

    def _resolve_name(self, node: ast.AST) -> str:
        """Return a dotted name for simple ``ast.Name`` or ``ast.Attribute`` nodes.
        Used for base classes and import aliases.
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts = []
            cur = node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            return ".".join(reversed(parts))
        return ""

class ProjectIngester:
    """Crawl a Python repo and return a list of :class:`CodeSymbol` objects.

    Parameters
    ----------
    root_dir: str
        Root directory of the project (absolute or relative).
    """

    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)
        self.ignore_dirs = default_ignore_dirs()

    def _module_name(self, file_path: str) -> str:
        return file_to_module(self.root_dir, file_path)

    def parse_file(self, file_path: str) -> List[CodeSymbol]:
        """Parse a single Python file and return its symbols.
        Non‑Python files are ignored.
        """
        if not is_python_file(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source)
        except Exception:
            # Corrupt file – skip silently
            return []
        module_name = self._module_name(file_path)
        # Create a module‑level symbol
        module_hash = hash_text(source)
        module_symbol = CodeSymbol(
            symbol_id=module_name,
            symbol_type=SymbolType.MODULE,
            file_path=file_path,
            name=module_name,
            start_line=1,
            end_line=len(source.splitlines()),
            parent_id=None,
            docstring=ast.get_docstring(tree),
            signature=None,
            content_hash=module_hash,
            dependencies=[],
        )
        visitor = _ASTVisitor(module_name, file_path, source)
        visitor.visit(tree)
        return [module_symbol] + visitor.symbols

    def crawl(self) -> List[CodeSymbol]:
        """Recursively walk ``root_dir`` and parse every Python file.
        Returns a flat list of symbols.
        """
        all_symbols: List[CodeSymbol] = []
        for root, dirs, files in os.walk(self.root_dir):
            # prune ignored directories
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs and not d.startswith('.')]
            for file in files:
                if file.lower().endswith('.py'):
                    path = os.path.join(root, file)
                    all_symbols.extend(self.parse_file(path))
        return all_symbols
