"""Python-version compatibility helpers for the Duckietown SDK.

This module installs a targeted import hook for Python 3.8 so callers
can import normal SDK and message modules without keeping per-module
compatibility forks in sync.
"""

from __future__ import annotations

import ast
import importlib.abc
import importlib.machinery
import re
import sys
from collections.abc import Iterable

_TARGET_PREFIXES = ("duckietown.sdk", "duckietown_messages")
_TYPING_ALIAS = "_duckietown_py38_typing"
_TYPING_NAME_MAP = {
    "Awaitable": "Awaitable",
    "Callable": "Callable",
    "ChainMap": "ChainMap",
    "Collection": "Collection",
    "Coroutine": "Coroutine",
    "Counter": "Counter",
    "defaultdict": "DefaultDict",
    "deque": "Deque",
    "Iterable": "Iterable",
    "Iterator": "Iterator",
    "Mapping": "Mapping",
    "MutableMapping": "MutableMapping",
    "OrderedDict": "OrderedDict",
    "Sequence": "Sequence",
    "dict": "Dict",
    "frozenset": "FrozenSet",
    "list": "List",
    "set": "Set",
    "tuple": "Tuple",
    "type": "Type",
}
_UNSUPPORTED_PY38_DATACLASS_KEYWORDS = {
    "kw_only",
    "match_args",
    "slots",
    "weakref_slot",
}

_COMPAT_FINDER = None


def enable_python38_compat() -> None:
    """Enable the Python 3.8 compatibility import hook once."""
    global _COMPAT_FINDER
    if sys.version_info >= (3, 9):
        return
    if _COMPAT_FINDER is not None:
        return
    _COMPAT_FINDER = _Py38CompatFinder(_TARGET_PREFIXES)
    sys.meta_path.insert(0, _COMPAT_FINDER)


def _unwrap_slice(node: ast.AST) -> ast.AST:
    index_type = getattr(ast, "Index", None)
    if index_type is not None and isinstance(node, index_type):
        return node.value
    return node


def _wrap_slice(node: ast.AST) -> ast.AST:
    index_type = getattr(ast, "Index", None)
    if index_type is not None and not isinstance(node, ast.slice):
        return index_type(value=node)
    return node


def _is_docstring(node: ast.AST) -> bool:
    if not isinstance(node, ast.Expr):
        return False
    value = node.value
    return isinstance(value, ast.Constant) and isinstance(value.value, str)


def _insert_typing_import(module: ast.Module) -> None:
    for statement in module.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "typing" and alias.asname == _TYPING_ALIAS:
                    return

    import_node = ast.Import(
        names=[ast.alias(name="typing", asname=_TYPING_ALIAS)],
    )
    insertion_index = 0
    if module.body and _is_docstring(module.body[0]):
        insertion_index = 1
    while insertion_index < len(module.body):
        statement = module.body[insertion_index]
        if isinstance(statement, ast.ImportFrom) and statement.module == "__future__":
            insertion_index += 1
            continue
        break
    module.body.insert(insertion_index, import_node)


_PEP695_CLASS_RE = re.compile(
    r"^(?P<indent>\s*)class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"\[(?P<params>[^\]]+)\](?P<bases>\([^\n]*\))?:",
    re.MULTILINE,
)


def _parse_type_params(params_text: str) -> list[str]:
    params = []
    for raw_param in params_text.split(","):
        param = raw_param.strip()
        if not param:
            continue
        if any(marker in param for marker in (":", "=", "(", ")", "[", "]", "*")):
            return []
        params.append(param)
    return params


def _rewrite_pep695_source(source: str) -> tuple[str, bool]:
    needs_typing_import = False

    def replace(match: re.Match[str]) -> str:
        nonlocal needs_typing_import

        params = _parse_type_params(match.group("params"))
        if not params:
            return match.group(0)

        needs_typing_import = True
        indent = match.group("indent")
        name = match.group("name")
        bases = match.group("bases")
        joined_params = ", ".join(params)
        generic_base = f"{_TYPING_ALIAS}.Generic[{joined_params}]"

        if bases:
            base_content = bases[1:-1].strip()
            if base_content:
                rewritten_bases = f"({base_content}, {generic_base})"
            else:
                rewritten_bases = f"({generic_base})"
        else:
            rewritten_bases = f"({generic_base})"

        typevar_lines = "\n".join(
            f"{indent}{param} = {_TYPING_ALIAS}.TypeVar({param!r})"
            for param in params
        )
        return f"{typevar_lines}\n\n{indent}class {name}{rewritten_bases}:"

    rewritten_source = _PEP695_CLASS_RE.sub(replace, source)
    return rewritten_source, needs_typing_import


class _Py38SyntaxTransformer(ast.NodeTransformer):

    def __init__(self) -> None:
        self.needs_typing_import = False

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        if node.annotation is not None:
            node.annotation = self._convert_expr(node.annotation)
        if node.value is not None:
            node.value = self.visit(node.value)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        node = self.generic_visit(node)
        node.decorator_list = [
            self._rewrite_dataclass_decorator(decorator)
            for decorator in node.decorator_list
        ]
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        if self._looks_like_type_alias(node):
            node.value = self._convert_expr(node.value)
            return node
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._visit_function(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._visit_function(node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        if node.annotation is not None:
            node.annotation = self._convert_expr(node.annotation)
        return node

    def _visit_function(self, node: ast.AST) -> ast.AST:
        function_node = self.generic_visit(node)
        returns = getattr(function_node, "returns", None)
        if returns is not None:
            function_node.returns = self._convert_expr(returns)
        return function_node

    def _convert_expr(self, expression: ast.AST) -> ast.AST:
        expression = _unwrap_slice(expression)

        if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
            return self._convert_union(expression)

        if isinstance(expression, ast.Subscript):
            converted_value = self._convert_expr(expression.value)
            converted_value = self._map_typing_base(converted_value)
            converted_slice = self._convert_expr(expression.slice)
            return ast.copy_location(
                ast.Subscript(
                    value=converted_value,
                    slice=_wrap_slice(converted_slice),
                    ctx=ast.Load(),
                ),
                expression,
            )

        if isinstance(expression, ast.Tuple):
            return ast.copy_location(
                ast.Tuple(
                    elts=[self._convert_expr(element) for element in expression.elts],
                    ctx=expression.ctx,
                ),
                expression,
            )

        if isinstance(expression, ast.List):
            return ast.copy_location(
                ast.List(
                    elts=[self._convert_expr(element) for element in expression.elts],
                    ctx=expression.ctx,
                ),
                expression,
            )

        return expression

    def _convert_union(self, expression: ast.BinOp) -> ast.AST:
        union_parts = []
        self._flatten_union(expression, union_parts)
        converted_parts = [self._convert_expr(part) for part in union_parts]
        non_none_parts = [part for part in converted_parts if not self._is_none_literal(part)]

        if len(converted_parts) == 2 and len(non_none_parts) == 1:
            optional_value = self._typing_attr("Optional")
            return ast.copy_location(
                ast.Subscript(
                    value=optional_value,
                    slice=_wrap_slice(non_none_parts[0]),
                    ctx=ast.Load(),
                ),
                expression,
            )

        union_value = self._typing_attr("Union")
        if len(converted_parts) == 1:
            union_slice = converted_parts[0]
        else:
            union_slice = ast.Tuple(elts=converted_parts, ctx=ast.Load())
        return ast.copy_location(
            ast.Subscript(
                value=union_value,
                slice=_wrap_slice(union_slice),
                ctx=ast.Load(),
            ),
            expression,
        )

    def _rewrite_dataclass_decorator(self, decorator: ast.AST) -> ast.AST:
        if not isinstance(decorator, ast.Call):
            return decorator
        if not self._is_dataclass_decorator(decorator.func):
            return decorator
        if not decorator.keywords:
            return decorator

        filtered_keywords = [
            keyword
            for keyword in decorator.keywords
            if keyword.arg not in _UNSUPPORTED_PY38_DATACLASS_KEYWORDS
        ]
        if len(filtered_keywords) == len(decorator.keywords):
            return decorator

        return ast.copy_location(
            ast.Call(
                func=decorator.func,
                args=decorator.args,
                keywords=filtered_keywords,
            ),
            decorator,
        )

    def _flatten_union(self, expression: ast.AST, union_parts: list[ast.AST]) -> None:
        if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
            self._flatten_union(expression.left, union_parts)
            self._flatten_union(expression.right, union_parts)
            return
        union_parts.append(expression)

    def _is_dataclass_decorator(self, expression: ast.AST) -> bool:
        if isinstance(expression, ast.Name):
            return expression.id == "dataclass"
        if isinstance(expression, ast.Attribute):
            return expression.attr == "dataclass"
        return False

    def _is_none_literal(self, expression: ast.AST) -> bool:
        expression = _unwrap_slice(expression)
        return isinstance(expression, ast.Constant) and expression.value is None

    def _map_typing_base(self, expression: ast.AST) -> ast.AST:
        if isinstance(expression, ast.Name):
            mapped_name = _TYPING_NAME_MAP.get(expression.id)
            if mapped_name is not None:
                return self._typing_attr(mapped_name)
            return expression

        if isinstance(expression, ast.Attribute):
            mapped_name = _TYPING_NAME_MAP.get(expression.attr)
            if mapped_name is not None and self._is_typing_attribute(expression.value):
                return self._typing_attr(mapped_name)

        return expression

    def _is_typing_attribute(self, expression: ast.AST) -> bool:
        parts = []
        current = expression
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        qualified_name = ".".join(reversed(parts))
        return qualified_name in {"collections", "collections.abc", "typing"}

    def _typing_attr(self, name: str) -> ast.AST:
        self.needs_typing_import = True
        return ast.Attribute(
            value=ast.Name(id=_TYPING_ALIAS, ctx=ast.Load()),
            attr=name,
            ctx=ast.Load(),
        )

    def _looks_like_type_alias(self, node: ast.Assign) -> bool:
        if len(node.targets) != 1:
            return False
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            return False
        if not target.id or not target.id[0].isupper():
            return False
        return self._contains_type_only_syntax(node.value)

    def _contains_type_only_syntax(self, expression: ast.AST) -> bool:
        expression = _unwrap_slice(expression)
        if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
            return True
        if isinstance(expression, ast.Subscript):
            if isinstance(expression.value, ast.Name) and expression.value.id in _TYPING_NAME_MAP:
                return True
            if isinstance(expression.value, ast.Attribute) and expression.value.attr in _TYPING_NAME_MAP:
                return True
            return self._contains_type_only_syntax(expression.slice)
        if isinstance(expression, (ast.Tuple, ast.List)):
            return any(self._contains_type_only_syntax(element) for element in expression.elts)
        return False


class _Py38CompatLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):  # type: ignore[override]
        source_path = self.get_filename(fullname)
        source_bytes = self.get_data(source_path)
        return self.source_to_code(source_bytes, source_path)

    def source_to_code(self, data, path, *, _optimize=-1):  # type: ignore[override]
        source = data.decode("utf-8") if isinstance(data, bytes) else data
        source, pep695_needs_typing_import = _rewrite_pep695_source(source)
        tree = ast.parse(source, filename=path)
        transformer = _Py38SyntaxTransformer()
        tree = transformer.visit(tree)
        if transformer.needs_typing_import or pep695_needs_typing_import:
            _insert_typing_import(tree)
        ast.fix_missing_locations(tree)
        return compile(
            tree,
            path,
            "exec",
            dont_inherit=True,
            optimize=_optimize,
        )


class _Py38CompatFinder(importlib.abc.MetaPathFinder):

    def __init__(self, prefixes: Iterable[str]) -> None:
        self._prefixes = tuple(prefixes)

    def find_spec(self, fullname, path=None, target=None):  # type: ignore[override]
        if not self._matches(fullname):
            return None

        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None:
            return None
        if not isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            return None

        spec.loader = _Py38CompatLoader(fullname, spec.origin)
        return spec

    def _matches(self, fullname: str) -> bool:
        if fullname == __name__ or fullname.startswith(__name__ + "."):
            return False
        for prefix in self._prefixes:
            if fullname == prefix or fullname.startswith(prefix + "."):
                return True
        return False
