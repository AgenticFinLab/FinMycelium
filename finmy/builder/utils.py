"""
Utilities for extracting dataclass schema blocks from Python source.

This module provides helpers to:
- Load Python source text from a file path (defaults to `structure.py` for convenience)
- Extract either all dataclass blocks or a specific subset plus their transitive
  dataclass dependencies referenced in field type annotations

Usage examples:

1) Extract all dataclass definitions
   >>> from finmy.builder.utils import load_python_text, extract_dataclass_blocks
   >>> spec = load_python_text()  # reads finmy/builder/structure.py by default
   >>> blocks = extract_dataclass_blocks(spec, mode="all")
   >>> print(blocks[:200])

2) Extract a specific dataclass and its referenced dataclass dependencies
   >>> spec = load_python_text()
   >>> blocks = extract_dataclass_blocks(spec, mode="single", target_classes=["Episode"])
   >>> print(blocks)

3) Use custom path (e.g., different schema file)
   >>> spec = load_python_text(path="/abs/path/to/another_structure.py")
   >>> blocks = extract_dataclass_blocks(spec)

Notes:
- When AST parsing fails (e.g., due to incomplete code), the extractor falls back to a
  regex-based method that simply concatenates all @dataclass blocks.
"""

import re
import ast
from pathlib import Path
from typing import Optional, List, Set, Dict, Any


def load_python_text(path: Optional[str | Path] = None) -> str:
    """Load Python source text.

    Behavior:
    - If `path` is None: load and concatenate all `*.py` files under the `builder` directory
      (i.e., the directory where this module resides).
    - If `path` is a file: load that file.
    - If `path` is a directory: load and concatenate all `*.py` files within it.

    Returns: Full file content as a single string. Empty string on failure.
    """
    base_dir = Path(__file__).parent
    if path is None:
        try:
            contents = []
            for py in sorted(base_dir.glob("*.py")):
                contents.append(py.read_text(encoding="utf-8"))
            return "\n".join(contents)
        except Exception:
            return ""

    p = Path(path)
    try:
        if p.is_file():
            return p.read_text(encoding="utf-8")
        if p.is_dir():
            contents = []
            for py in sorted(p.glob("*.py")):
                contents.append(py.read_text(encoding="utf-8"))
            return "\n".join(contents)
        return ""
    except Exception:
        return ""


def extract_dataclass_blocks(
    spec: str,
    mode: str = "all",
    target_classes: Optional[List[str]] = None,
) -> str:
    """Extract dataclass blocks from Python source.

    Parameters:
    - spec: Full Python source text containing @dataclass definitions
    - mode:
        - "all": return all dataclass blocks
        - "single": return only the target dataclass blocks and any dataclass
          transitively referenced by their field type annotations
    - target_classes: Class names to start from when mode=="single"

    Returns: Concatenated dataclass blocks as a string

    Implementation details:
    - Uses AST to find class definitions decorated with @dataclass
    - Collects type names from field annotations to resolve dependencies
    - Preserves original order of appearance when emitting blocks
    - Falls back to regex if AST parsing fails
    """

    lines = spec.splitlines()

    try:
        tree = ast.parse(spec)
    except SyntaxError:
        blocks = re.findall(r"@dataclass[\s\S]*?(?=\n@dataclass|\Z)", spec)
        return ("\n".join(blocks)).strip()

    def is_dataclass(node: ast.ClassDef) -> bool:
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "dataclass":
                return True
            if isinstance(dec, ast.Attribute) and dec.attr == "dataclass":
                return True
        return False

    def collect_type_names(annotation: Optional[ast.AST], acc: Set[str]) -> None:
        if annotation is None:
            return
        if isinstance(annotation, ast.Name):
            acc.add(annotation.id)
        elif isinstance(annotation, ast.Attribute):
            acc.add(annotation.attr)
            if isinstance(annotation.value, ast.Name):
                acc.add(annotation.value.id)
        elif isinstance(annotation, ast.Subscript):
            collect_type_names(annotation.value, acc)
            sub = annotation.slice
            if isinstance(sub, ast.Tuple):
                for elt in sub.elts:
                    collect_type_names(elt, acc)
            else:
                collect_type_names(sub, acc)
        elif isinstance(annotation, ast.BinOp):
            # Supports union types like X | Y (PEP 604)
            collect_type_names(annotation.left, acc)
            collect_type_names(annotation.right, acc)
        elif isinstance(annotation, ast.Call):
            collect_type_names(annotation.func, acc)
            for arg in getattr(annotation, "args", []) or []:
                collect_type_names(arg, acc)
        # Ignore other node types

    class_map: Dict[str, Dict[str, Any]] = {}
    class_order: List[str] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and is_dataclass(node):
            name = node.name
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
            if start is None or end is None:
                continue
            block = "\n".join(lines[start - 1 : end])
            deps: Set[str] = set()
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign):
                    collect_type_names(stmt.annotation, deps)
                elif isinstance(stmt, ast.Assign):
                    if isinstance(stmt.value, ast.Call):
                        collect_type_names(stmt.value.func, deps)
                        for arg in stmt.value.args:
                            collect_type_names(arg, deps)
                        for kw in stmt.value.keywords or []:
                            collect_type_names(kw.value, deps)
            class_map[name] = {"block": block, "deps": deps}
            class_order.append(name)

    if mode == "all" or not class_map:
        return ("\n".join([class_map[n]["block"] for n in class_order])).strip()

    if mode == "single":
        if not target_classes:
            return ""
        target_set: Set[str] = set(target_classes)
        resolved: Set[str] = set()
        queue: List[str] = list(target_set)
        while queue:
            cur = queue.pop(0)
            if cur in resolved:
                continue
            if cur not in class_map:
                resolved.add(cur)
                continue
            resolved.add(cur)
            for dep in class_map[cur]["deps"]:
                if dep in class_map and dep not in resolved:
                    queue.append(dep)
        emit = [class_map[n]["block"] for n in class_order if n in resolved]
        return ("\n".join(emit)).strip()

    return ""
