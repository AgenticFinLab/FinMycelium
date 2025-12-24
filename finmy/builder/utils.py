"""
Utilities for loading Python source and extracting/filtering dataclass blocks.

Notes:
- If AST parsing fails (e.g., due to incomplete code), `extract_dataclass_blocks` falls back
  to a regex that concatenates all `@dataclass` blocks.
"""

import re
import json
import ast
from pathlib import Path
from typing import List, Set, Dict, Any, Optional

from finmy.builder.constant import OTHER_TOKEN_NUM, ESTIMATE_PER_TOKEN_TIME_COST


def load_python_text(path: str | Path) -> str:
    """Load Python source text from a required path.

    Behavior:
    - If `path` is a file: returns that file's text.
    - If `path` is a directory: loads and concatenates all `*.py` files within the directory
      (sorted by filename) into a single string.

    Returns:
    - The file/directory content as a single string. Returns empty string on failure or when
      `path` exists but is neither a file nor a directory.

    Examples:
    >>> from pathlib import Path
    >>> text = load_python_text(Path("finmy/builder/structure.py"))
    >>> isinstance(text, str) and "@dataclass" in text
    True

    >>> text = load_python_text(Path("finmy/builder/"))
    >>> isinstance(text, str)
    True
    """
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
    code_text: str,
    mode: str = "all",
    target_classes: Optional[List[str]] = None,
) -> str:
    """Extract dataclass blocks from Python source text.

    Parameters:
    - code_text: Python source text containing `@dataclass` class definitions.
    - mode:
      - "all": return all dataclass blocks in the order they appear.
      - "single": return only the target dataclass blocks and any dataclass transitively
        referenced by their field type annotations.
    - target_classes: Class names to start from when `mode == "single"`.

    Returns:
    - Concatenated dataclass blocks as a single string. Empty string if nothing found.

    Behavior:
    - Parses with `ast` and collects `@dataclass` class blocks by line range, preserving order.
    - Resolves dependencies in "single" mode by walking field annotations and union/subscript types.
    - Falls back to regex extraction when `ast.parse` fails, concatenating `@dataclass` blocks.

    Examples:
    >>> text = load_python_text("finmy/builder/structure.py")
    >>> all_blocks = extract_dataclass_blocks(text, mode="all")
    >>> "class EventStage" in all_blocks and "class Episode" in all_blocks
    True

    >>> single_blocks = extract_dataclass_blocks(text, mode="single", target_classes=["Episode"])
    >>> "class Episode" in single_blocks
    True
    """

    lines = code_text.splitlines()

    try:
        tree = ast.parse(code_text)
    except SyntaxError:
        blocks = re.findall(r"@dataclass[\s\S]*?(?=\n@dataclass|\Z)", code_text)
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


def filter_dataclass_fields(
    code_text: str, include: Dict[str, Optional[List[str]]]
) -> str:
    """Filter dataclass definitions to include only specified fields per class.

    Parameters:
    - code_text: Python source text containing `@dataclass` classes.
    - include: Mapping of `ClassName -> List[field_name]` to retain. Use `None` or an empty list to retain all fields for that class header (not recommended for filtering). Classes not present in the mapping are omitted.

    Returns:
    - Concatenated text of filtered `@dataclass` class definitions, preserving decorators and
      class headers, and including only the selected field assignment lines. Class docstrings and
      non-field statements are omitted.

    Notes:
    - Field detection covers annotated assignments (`AnnAssign`) and simple assignments (`Assign`).
    - Retains the contiguous comment lines immediately above each retained field (lines starting with `#`).
      Stops when encountering a non-comment or a blank line.
    - The function preserves the original order of class definitions.

    Example:
    >>> text = load_python_text("finmy/builder/structure.py")
    >>> filtered = filter_dataclass_fields(text, {
    ...     "EventStage": ["stage_id", "name", "index_in_event"],
    ...     "Episode": ["episode_id", "name", "index_in_stage"],
    ... })
    >>> "class EventStage" in filtered and "class Episode" in filtered
    True
    >>> "episodes:" in filtered
    False
    """
    lines = code_text.splitlines()
    try:
        tree = ast.parse(code_text)
    except SyntaxError:
        return ""

    def is_dataclass(node: ast.ClassDef) -> bool:
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "dataclass":
                return True
            if isinstance(dec, ast.Attribute) and dec.attr == "dataclass":
                return True
        return False

    blocks: List[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not is_dataclass(node):
            continue
        name = node.name
        if name not in include:
            continue
        allow = include[name]
        allow_set = set(allow) if allow else set()
        deco_lines = [
            getattr(d, "lineno", node.lineno) for d in node.decorator_list
        ] or [node.lineno]
        start = min(deco_lines)
        # Include decorator lines and the class header line
        header = lines[start - 1 : node.lineno + 1]
        # Include class docstring if present, trimming example lines that reference removed fields
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(getattr(node.body[0], "value", None), ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            ds = getattr(node.body[0], "lineno", None)
            de = getattr(node.body[0], "end_lineno", None)
            if ds and de:
                # Determine all field names in the class
                all_fields: Set[str] = set()
                for st in node.body:
                    if isinstance(st, ast.AnnAssign):
                        tgt = getattr(st, "target", None)
                        fn = (
                            tgt.id
                            if isinstance(tgt, ast.Name)
                            else (tgt.attr if isinstance(tgt, ast.Attribute) else None)
                        )
                        if fn:
                            all_fields.add(fn)
                    elif isinstance(st, ast.Assign):
                        tgs = getattr(st, "targets", []) or []
                        t0 = tgs[0] if tgs else None
                        fn = t0.id if isinstance(t0, ast.Name) else None
                        if fn:
                            all_fields.add(fn)
                removed_fields: Set[str] = set()
                if allow_set:
                    removed_fields = all_fields - allow_set
                # Filter docstring lines: keep everything before 'Example:' intact;
                # in the example block, drop lines mentioning removed field names
                doc_lines = lines[ds - 1 : de]
                filtered_doc: List[str] = []
                in_example = False
                # Enhanced block skipping for removed fields within Example:
                skipping_field_block = False
                await_bracket_start = False  # true until we see the first opening bracket after field line
                bracket_depth = (
                    0  # tracks nested [] and {} depth for the removed field block
                )
                for dl in doc_lines:
                    if not in_example and "Example:" in dl:
                        in_example = True
                        filtered_doc.append(dl)
                        continue
                    if in_example and removed_fields:
                        # If currently skipping a removed field block, continue until bracket_depth returns to zero.
                        if skipping_field_block:
                            # Update bracket depth based on occurrences in the current line
                            opens = dl.count("[") + dl.count("{")
                            closes = dl.count("]") + dl.count("}")
                            # If we were awaiting the bracket start, detect it here
                            if await_bracket_start and opens > 0:
                                await_bracket_start = False
                            bracket_depth += opens - closes
                            # Once depth returns to zero (or negative due to formatting), stop skipping after this line
                            if not await_bracket_start and bracket_depth <= 0:
                                skipping_field_block = False
                                bracket_depth = 0
                            # Always skip the current line while in skipping mode
                            continue
                        # Not currently skipping; check if this line declares a removed field
                        field_line_match = False
                        for rf in removed_fields:
                            # match patterns like "field": or field:
                            if re.search(
                                rf"[\"']{re.escape(rf)}[\"']\s*:", dl
                            ) or re.search(rf"\b{re.escape(rf)}\b\s*:", dl):
                                field_line_match = True
                                break
                        if field_line_match:
                            # Start skipping this removed field block
                            opens = dl.count("[") + dl.count("{")
                            closes = dl.count("]") + dl.count("}")
                            bracket_depth = opens - closes
                            # If the bracket does not start on the same line, wait for the next line to begin depth tracking
                            await_bracket_start = bracket_depth == 0
                            # If bracket starts immediately, ensure we are not awaiting
                            if bracket_depth > 0:
                                await_bracket_start = False
                            skipping_field_block = True
                            # Skip the current line
                            continue
                        # If no match and not skipping, we keep the line
                    # Default: keep the line
                    filtered_doc.append(dl)
                header.extend(filtered_doc)
        # Deduplicate consecutive identical lines in header
        if header:
            dedup_header: List[str] = []
            for hl in header:
                if not dedup_header or dedup_header[-1] != hl:
                    dedup_header.append(hl)
            header = dedup_header
        body: List[str] = []
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign):
                target = getattr(stmt, "target", None)
                fname = (
                    target.id
                    if isinstance(target, ast.Name)
                    else (target.attr if isinstance(target, ast.Attribute) else None)
                )
                if not allow_set or (fname in allow_set):
                    s = getattr(stmt, "lineno", None)
                    e = getattr(stmt, "end_lineno", None)
                    if s and e:
                        # include preceding contiguous comment lines (starting with '#') inside class
                        prev = s - 1
                        pre_lines: List[str] = []
                        while prev > (node.lineno) and prev - 1 >= 0:
                            line = lines[prev - 1]
                            if line.lstrip().startswith("#"):
                                pre_lines.insert(0, line)
                                prev -= 1
                                continue
                            break
                        body.extend(pre_lines)
                        body.extend(lines[s - 1 : e])
            elif isinstance(stmt, ast.Assign):
                targets = getattr(stmt, "targets", []) or []
                t0 = targets[0] if targets else None
                fname = t0.id if isinstance(t0, ast.Name) else None
                if fname is not None and (not allow_set or (fname in allow_set)):
                    s = getattr(stmt, "lineno", None)
                    e = getattr(stmt, "end_lineno", None)
                    if s and e:
                        prev = s - 1
                        pre_lines: List[str] = []
                        while prev > (node.lineno) and prev - 1 >= 0:
                            line = lines[prev - 1]
                            if line.lstrip().startswith("#"):
                                pre_lines.insert(0, line)
                                prev -= 1
                                continue
                            break
                        body.extend(pre_lines)
                        body.extend(lines[s - 1 : e])
        blocks.append("\n".join(header + body))

    return ("\n\n".join(blocks)).strip()


def extract_json_response(response_text: str) -> Dict[str, Any]:
    """Extract a JSON object/array from an LLM response text.

    Behavior:
    - Strips markdown code fences if present (``` or ```json).
    - Attempts to parse the cleaned text directly as JSON.
    - If that fails, searches for the longest JSON object/array substring and parses it.
    - Raises ValueError if no valid JSON can be found.

    Examples:
    >>> t = "Response: OK. {\"b\": [1,2,3]}"
    >>> extract_json_response(t)
    {'b': [1, 2, 3]}
    """
    clean_text = response_text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_text, re.DOTALL)
    if m:
        clean_text = m.group(1)
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError as e:
        matches = re.findall(r"(\{.*\}|\[.*\])", clean_text, re.DOTALL)
        if matches:
            longest = max(matches, key=len)
            return json.loads(longest)
        raise ValueError(f"Failed to parse JSON from response: {e}") from e


def estimate_time_to_complete(
    str_list: List[str],
) -> int:
    """Estimate the time to complete the reconstruction based on the content length.

    Parameters:
    - content_length: The length of the content in characters.

    Returns:
    - The estimated time to complete the reconstruction in minutes.
    """
    all_content = " ".join(str_list)

    # Calculate the length of the build input,
    # considering the space between words and the length of the words
    # ( not precisely, just approximately)
    build_input_length = 0
    last_word = ""
    for i in all_content:
        if i.isspace():
            if not last_word.isspace():
                build_input_length += 1
            last_word = i
        elif i.isascii():
            if not last_word.isspace():
                continue
            last_word = i
        else:
            last_word = i
            build_input_length += 1

    return round((build_input_length + OTHER_TOKEN_NUM) * ESTIMATE_PER_TOKEN_TIME_COST)
