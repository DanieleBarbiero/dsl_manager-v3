"""Deterministic Java code units through tree-sitter-java (optional extra).

Only declarations and statically evident calls are emitted: no classpath, no
type inference, no bytecode. A call whose target is not lexically certain is
counted in a diagnostic and never promoted to a dependency. tree-sitter is
imported lazily, so nothing is loaded while the java_analysis flag is off.
"""

from __future__ import annotations
import bisect
import itertools
import re

from dslm3.common import DomainError
from dslm3.parsers.base import ParseResult, location

PARSER = "java/1"
JAVA_HINT = re.compile(
    r"\bLANGUAGE\s+JAVA\b|\bJAVA\s+(?:SOURCE|CLASS|RESOURCE)\b", re.I
)
# Headless source (e.g. USER_SOURCE of a JAVA SOURCE): comments, then a package,
# an import or a top-level type. Case-sensitive on purpose: SQL is not Java.
JAVA_HEADLESS = re.compile(
    r"\A\ufeff?\s*(?:(?://[^\n]*|/\*[\s\S]*?\*/)\s*)*"
    r"(?:package\s+[\w.]+\s*;|import\s+(?:static\s+)?[\w.]+(?:\.\*)?\s*;"
    r"|(?:(?:public|final|abstract|strictfp)\s+)*(?:class|interface|enum|record)\s+[A-Za-z_$][\w$]*)"
)
TYPE_DECLS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}
TYPE_BODIES = {
    "class_body",
    "interface_body",
    "enum_body_declarations",
    "annotation_type_body",
}
METHODS = {
    "method_declaration": "java_method",
    "constructor_declaration": "java_constructor",
    "compact_constructor_declaration": "java_constructor",
}
JAVA_LANG = frozenset(
    "System Runtime Thread String StringBuilder StringBuffer Math StrictMath "
    "Integer Long Short Byte Double Float Boolean Character Object Class "
    "ClassLoader Enum Process ProcessBuilder ProcessHandle Number Void Throwable "
    "Exception Error RuntimeException Iterable Comparable Record CharSequence "
    "ThreadLocal InheritableThreadLocal ThreadGroup Package Module ModuleLayer "
    "StackWalker StackTraceElement SecurityManager".split()
)
OBJECT_METHODS = frozenset(
    "toString hashCode equals getClass wait notify notifyAll clone finalize".split()
)
PLATFORM = ("java.", "javax.")
_FQN = re.compile(r"[a-z_]\w*(?:\.[a-z_]\w*)*\.[A-Z][\w$]*")
_NAME_CHAIN = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+")
_JAVA_TOKENS = re.compile(
    r'//[^\n]*|/\*[\s\S]*?(?:\*/|\Z)|"""(?:\\[\s\S]|[^\\])*?(?:"""|\Z)'
    r'|"(?:\\.|[^"\\\n])*"?|\'(?:\\.|[^\'\\\n])*\'?'
)
_LANGUAGE = []


def _parser():
    """A fresh tree-sitter parser, or None when the optional extra is missing."""
    if not _LANGUAGE:
        try:
            import tree_sitter_java
            from tree_sitter import Language

            _LANGUAGE.append(Language(tree_sitter_java.language()))
        except (ImportError, OSError, ValueError, TypeError):
            _LANGUAGE.append(None)
    if _LANGUAGE[0] is None:
        return None
    from tree_sitter import Parser

    return Parser(_LANGUAGE[0])


def available() -> bool:
    return _parser() is not None


def grammar_version() -> str | None:
    if _parser() is None:
        return None
    from importlib.metadata import PackageNotFoundError, version

    try:
        return "tree-sitter-java/" + version("tree-sitter-java")
    except PackageNotFoundError:
        return "tree-sitter-java/unknown"


def mask_java(text: str) -> str:
    """Preserve offsets/newlines while hiding Java comments and literals."""
    return _JAVA_TOKENS.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)


def has_java_units(text: str) -> bool:
    """Oracle Java DDL or call specifications outside SQL comments and literals."""
    if not JAVA_HINT.search(text):
        return False
    from dslm3.parsers.sql import JAVA_CALL_SPEC, JAVA_UNIT, mask_literals

    masked = mask_literals(text)
    return bool(JAVA_UNIT.search(masked) or JAVA_CALL_SPEC.search(masked))


def looks_like_java(text: str) -> bool:
    """Lexical gate on the start of the file, then grammar confirmation."""
    if not JAVA_HEADLESS.match(text):
        return False
    parser = _parser()
    if parser is None:
        return False
    root = parser.parse(text.encode("utf-8", "surrogatepass")).root_node
    return any(c.type in TYPE_DECLS for c in root.named_children)


def parse_java(text: str) -> ParseResult:
    result = ParseResult(PARSER)
    analyze(result, text, text, 0)
    return result


def parse_sql_java(
    text: str, dialect: str = "auto", schema: dict | None = None
) -> ParseResult:
    """SQL dispatch with java_analysis on; without tree-sitter-java it degrades
    to the flag-off parse plus a diagnostic."""
    from dslm3.parsers.sql import parse_sql

    if _parser() is None:
        result = parse_sql(text, dialect, schema)
        if has_java_units(text) or JAVA_HEADLESS.match(text):
            result.warn(
                "java_parser_unavailable",
                "tree-sitter-java non installato: il Java resta analizzato come SQL.",
            )
        return result
    if looks_like_java(text):
        result = parse_java(text)
        result.warn(
            "java_headless_source_detected",
            "Sorgente Java senza header CREATE: analizzato come Java.",
        )
        return result
    return parse_sql(text, dialect, schema, java=True)


def _text(node) -> str:
    return node.text.decode("utf-8", "surrogatepass")


def _compact(node) -> str | None:
    return re.sub(r"\s+", "", _text(node)) if node is not None else None


def _signature(parameters) -> str:
    types = []
    for p in parameters.named_children if parameters is not None else []:
        if p.type == "formal_parameter":
            dims = p.child_by_field_name("dimensions")
            types.append(_compact(p.child_by_field_name("type")) + (_compact(dims) or ""))
        elif p.type == "spread_parameter":
            kind = next(
                c
                for c in p.named_children
                if c.type not in {"modifiers", "variable_declarator"}
            )
            types.append(_compact(kind) + "...")
    return "(" + ",".join(types) + ")"


class _Scope:
    """A class body: its binary name and what an unqualified name may hit."""

    __slots__ = (
        "name",
        "simple",
        "methods",
        "members",
        "implicit",
        "has_super",
        "signature",
    )

    def __init__(self, name, simple, body, has_super, components=None):
        self.name, self.simple, self.has_super = name, simple, has_super
        self.methods, self.members = set(), {}
        nodes = list(body.named_children) if body is not None else []
        for child in list(nodes):
            if child.type == "enum_body_declarations":
                nodes.extend(child.named_children)
        for child in nodes:
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            if child.type == "method_declaration":
                self.methods.add(_text(name_node))
            elif child.type in TYPE_DECLS:
                self.members[_text(name_node)] = name + "." + _text(name_node)
        params = components.named_children if components is not None else []
        # Record accessors not written in the body exist only in bytecode.
        self.implicit = {
            _text(p.child_by_field_name("name"))
            for p in params
            if p.type == "formal_parameter"
        } - self.methods
        self.signature = _signature(components) if components is not None else None


def _has_super(node, kind) -> bool:
    if kind in {"enum", "annotation"}:
        return True
    if kind == "interface":
        return any(c.type == "extends_interfaces" for c in node.named_children)
    fields = ("interfaces",) if kind == "record" else ("superclass", "interfaces")
    return any(node.child_by_field_name(f) is not None for f in fields)


def _unit_facts(root) -> dict:
    """Package, imports, top-level types, and every name that may denote a
    variable or a local type anywhere in the unit (conservative, not scoped)."""
    facts = {
        "package": None,
        "single": {},
        "static": {},
        "on_demand": False,
        "tops": set(),
        "variables": set(),
        "local_types": set(),
    }
    for child in root.named_children:
        name = next(
            (
                c
                for c in child.named_children
                if c.type in {"scoped_identifier", "identifier"}
            ),
            None,
        )
        if child.type == "package_declaration":
            facts["package"] = _compact(name)
        elif child.type == "import_declaration" and name is not None:
            tokens = {c.type for c in child.children}
            full = _compact(name)
            if "asterisk" in tokens:
                facts["on_demand"] = facts["on_demand"] or "static" not in tokens
                continue
            table = facts["static" if "static" in tokens else "single"]
            simple = full.rsplit(".", 1)[-1]
            # One simple name imported from two classes: no certain target.
            table[simple] = full if table.get(simple, full) == full else None
        elif child.type in TYPE_DECLS and child.child_by_field_name("name"):
            facts["tops"].add(_text(child.child_by_field_name("name")))
    named = {
        "variable_declarator",
        "formal_parameter",
        "catch_formal_parameter",
        "resource",
        "enhanced_for_statement",
        "instanceof_expression",
        "enum_constant",
    }
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.named_children)
        t = node.type
        if t in named:
            name = node.child_by_field_name("name")
            if name is not None and name.type == "identifier":
                facts["variables"].add(_text(name))
        elif t in {"type_pattern", "record_pattern_component", "inferred_parameters"}:
            facts["variables"].update(
                _text(c) for c in node.named_children if c.type == "identifier"
            )
        elif t == "lambda_expression":
            params = node.child_by_field_name("parameters")
            if params is not None and params.type == "identifier":
                facts["variables"].add(_text(params))
        elif (
            t in TYPE_DECLS
            and node.parent is not None
            and node.parent.type not in TYPE_BODIES | {"program", "ERROR"}
            and node.child_by_field_name("name") is not None
        ):
            facts["local_types"].add(_text(node.child_by_field_name("name")))
    return facts


def analyze(
    result: ParseResult,
    body: str,
    source: str,
    offset: int,
    container: str | None = None,
) -> list[str]:
    """Append Java evidence for `body`, located at `offset` in `source`.

    Returns the binary names of the top-level types, in source order.
    """
    parser = _parser()
    if parser is None:
        raise DomainError(
            "java_parser_unavailable",
            "Analisi Java attiva ma tree-sitter-java non installato (extra 'java').",
        )
    tree = parser.parse(body.encode("utf-8", "surrogatepass"))
    # tree-sitter reports UTF-8 byte offsets; locators are character offsets.
    starts = (
        None
        if body.isascii()
        else list(
            itertools.accumulate(
                (len(ch.encode("utf-8", "surrogatepass")) for ch in body), initial=0
            )
        )
    )

    def span(node):
        a, b = node.start_byte, node.end_byte
        if starts is not None:
            a, b = bisect.bisect_left(starts, a), bisect.bisect_left(starts, b)
        return body[a:b], location(source, offset + a, offset + b)

    facts = _unit_facts(tree.root_node)
    package, variables = facts["package"], facts["variables"]
    counters, tops, platform = {}, [], {}
    unresolved = 0

    def qualifiable(name):
        return (
            name[:1].isupper()
            and not (len(name) > 1 and name.isupper())
            and name not in variables
            and name not in facts["local_types"]
        )

    def type_named(name, scopes):
        """(binary name, basis) of a simple type name, or None if not certain."""
        for i, scope in enumerate(scopes):
            found = scope.members.get(name) or (
                scope.name if scope.simple == name else None
            )
            if found:
                # A nested scope with supertypes may inherit a homonymous type.
                if any(s.has_super for s in scopes[:i]):
                    return None
                return found, "static_qualifier"
        blocked = any(s.has_super for s in scopes)
        if name in facts["tops"]:
            if blocked:
                return None
            return (package + "." + name if package else name), "static_qualifier"
        if name in facts["single"]:
            full = facts["single"][name]
            if blocked or full is None:
                return None
            return full, "platform" if full.startswith(PLATFORM) else "single_type_import"
        if name in JAVA_LANG:
            return "java.lang." + name, "platform"
        if blocked or facts["on_demand"]:
            return None
        if package:
            return package + "." + name, "same_package"
        return name, "static_qualifier"

    def unqualified(member, scopes):
        inner = scopes[0]
        if member in OBJECT_METHODS and member not in inner.methods:
            return None if inner.has_super else ("java.lang.Object." + member, "platform")
        for i, scope in enumerate(scopes):
            if member in scope.methods:
                if any(s.has_super for s in scopes[:i]):
                    return None
                basis = "same_class" if i == 0 else "enclosing_class"
                return scope.name + "." + member, basis
            if member in scope.implicit:
                return None
        if any(s.has_super for s in scopes):
            return None
        full = facts["static"].get(member)
        if full is None:
            return None
        return full, "platform" if full.startswith(PLATFORM) else "static_import"

    def call_target(node, scopes):
        member = _text(node.child_by_field_name("name"))
        receiver = node.child_by_field_name("object")
        if receiver is None:
            return unqualified(member, scopes)
        if receiver.type == "this":
            inner = scopes[0]
            if member in inner.methods:
                return inner.name + "." + member, "same_class"
            if member in OBJECT_METHODS and not inner.has_super:
                return "java.lang.Object." + member, "platform"
            return None
        if receiver.type == "identifier":
            name = _text(receiver)
            found = type_named(name, scopes) if qualifiable(name) else None
            return (found[0] + "." + member, found[1]) if found else None
        if receiver.type != "field_access":
            return None
        chain = _compact(receiver)
        first = chain.split(".", 1)[0]
        if not _NAME_CHAIN.fullmatch(chain) or first in {"this", "super"} | variables:
            return None
        if qualifiable(first):
            found = type_named(first, scopes)
            if found and found[1] == "platform":
                return found[0] + chain[len(first) :] + "." + member, "platform"
            return None  # static field of a project type: its type is unknown
        if not _FQN.fullmatch(chain):
            return None
        if chain.startswith(PLATFORM):
            return chain + "." + member, "platform"
        if any(s.has_super for s in scopes):
            return None
        return chain + "." + member, "qualified_name"

    def declare_type(node, scopes, method):
        kind = TYPE_DECLS[node.type]
        simple = _text(node.child_by_field_name("name"))
        parent = node.parent.type if node.parent is not None else "program"
        data = {"unit_type": "java_" + kind, "dialect": "java", "container": container}
        if not scopes or parent == "program":
            name = package + "." + simple if package else simple
            if parent == "program":
                tops.append(name)
        elif parent in TYPE_BODIES or parent == "ERROR":
            name = scopes[0].name + "." + simple
        else:  # local type: javac numbers per (enclosing class, simple name)
            key = (scopes[0].name, simple)
            counters[key] = counters.get(key, 0) + 1
            name = f"{scopes[0].name}${counters[key]}{simple}"
            data["enclosing_method"] = method
        text, loc = span(node)
        result.add("java_class", text, {"name": name, **data}, loc)
        components = node.child_by_field_name("parameters") if kind == "record" else None
        members = node.child_by_field_name("body")
        return members, _Scope(name, simple, members, _has_super(node, kind), components)

    def declare_anonymous(node, members, scopes, method):
        key = (scopes[0].name, "")
        counters[key] = counters.get(key, 0) + 1
        name = f"{scopes[0].name}${counters[key]}"
        if node.type == "enum_constant":
            supertype = scopes[0].name
        else:
            supertype = _compact(node.child_by_field_name("type"))
        text, loc = span(node)
        data = {
            "name": name,
            "unit_type": "java_anonymous_class",
            "dialect": "java",
            "container": container,
            "extends": supertype,
            "enclosing_method": method,
        }
        result.add("java_class", text, data, loc)
        return _Scope(name, None, members, True)

    def declare_method(node, scope):
        name = scope.name + "." + _text(node.child_by_field_name("name"))
        if node.type == "compact_constructor_declaration":
            signature = scope.signature or "()"
        else:
            signature = _signature(node.child_by_field_name("parameters"))
        modifiers = next((c for c in node.named_children if c.type == "modifiers"), None)
        returns = _compact(node.child_by_field_name("type"))
        if returns is not None and node.child_by_field_name("dimensions") is not None:
            returns += _compact(node.child_by_field_name("dimensions"))
        text, loc = span(node)
        data = {
            "name": name,
            "parent_unit": scope.name,
            "unit_type": METHODS[node.type],
            "dialect": "java",
            "container": container,
            "signature": signature,
            "modifiers": [
                c.type for c in (modifiers.children if modifiers else []) if not c.is_named
            ],
            "return_type": returns,
        }
        result.add("java_method", text, data, loc)
        return name

    # Iterative pre-order visit: deep expressions must not hit the recursion limit.
    stack = [(tree.root_node, (), None, False)]
    while stack:
        node, scopes, method, in_error = stack.pop()
        t = node.type
        children = node.children
        inner = [(scopes, method)] * len(children)
        if t == "ERROR" and not in_error:
            text, loc = span(node)
            owner = method or (scopes[0].name if scopes else container)
            result.add("java_unparsed", text, {"owner": owner}, loc)
            in_error = True
        elif t in TYPE_DECLS and node.child_by_field_name("name") is not None:
            members, scope = declare_type(node, scopes, method)
            inner = [
                ((scope, *scopes) if members is not None and c.id == members.id else scopes, None)
                for c in children
            ]
        elif t in {"object_creation_expression", "enum_constant"} and scopes:
            if t == "enum_constant":
                members = node.child_by_field_name("body")
            else:
                members = next((c for c in children if c.type == "class_body"), None)
            if members is not None:
                scope = declare_anonymous(node, members, scopes, method)
                inner = [
                    ((scope, *scopes), None) if c.id == members.id else (scopes, method)
                    for c in children
                ]
        elif t in METHODS and scopes and node.child_by_field_name("name") is not None:
            inner = [(scopes, declare_method(node, scopes[0]))] * len(children)
        elif t == "method_invocation":
            found = call_target(node, scopes) if scopes else None
            if found is None:
                unresolved += 1
            elif found[1] == "platform":
                platform[found[0]] = platform.get(found[0], 0) + 1
            else:
                text, loc = span(node)
                data = {
                    "source": method or scopes[0].name,
                    "relation_type": "calls",
                    "target": found[0],
                    "target_kind": "java_unit",
                    "basis": found[1],
                }
                result.add("java_dependency", text, data, loc)
        for i in range(len(children) - 1, -1, -1):
            stack.append((children[i], *inner[i], in_error))
    if platform:
        calls = result.metadata.setdefault("java_platform_calls", {})
        for target, count in platform.items():
            calls[target] = calls.get(target, 0) + count
    result.metadata["java_grammar"] = grammar_version()
    if unresolved:
        result.warn(
            "java_receiver_type_unresolved",
            "Chiamate Java senza tipo statico del ricevente: non promosse a dipendenza.",
            count=unresolved,
            unit=container,
        )
    if tree.root_node.has_error:
        result.status = "partial"
        result.warn(
            "java_syntax_error",
            "Sorgente Java con errori sintattici: porzioni conservate come java_unparsed.",
            unit=container,
        )
    return tops
