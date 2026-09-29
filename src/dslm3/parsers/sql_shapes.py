"""Versioned, lossless semantic projections of SQLGlot ASTs (never execute SQL)."""

from __future__ import annotations
from enum import Enum

from sqlglot import exp
from dslm3.common import uid

VERSION = "4"


def identifier(node):
    if isinstance(node, (exp.Table, exp.Column)):
        return ".".join(identifier(p) for p in node.parts)
    if isinstance(node, exp.Identifier):
        return (
            '"' + node.name.replace('"', '""') + '"'
            if node.args.get("quoted")
            else node.name.upper()
        )
    return node.sql() if isinstance(node, exp.Expression) else str(node)


def literal(node, dialect):
    if isinstance(node, exp.Paren):
        return literal(node.this, dialect)
    if isinstance(node, exp.Null):
        return {"type": "null", "value": None}
    if isinstance(node, exp.Boolean):
        return {"type": "boolean", "value": node.this}
    if isinstance(node, exp.Literal):
        if node.is_string:
            if node.this == "" and dialect == "oracle":
                return {"type": "null", "value": None, "source_literal": "empty_string"}
            return {"type": "string", "value": node.this}
        return {"type": "number", "value": node.this}
    if isinstance(node, exp.Neg):
        value = literal(node.this, dialect)
        if value and value["type"] == "number" and not value["value"].startswith("-"):
            return {"type": "number", "value": "-" + value["value"]}
    return None


def expression(node, dialect=None):
    """Small stable AST independent of SQLGlot's serialized implementation metadata."""
    if node is None:
        return None
    if isinstance(node, Enum):
        return node.value
    if not isinstance(node, exp.Expression):
        return node
    value = literal(node, dialect)
    if value is not None:
        return {"node": "literal", **value}
    if isinstance(node, exp.Identifier):
        return {
            "node": "identifier",
            "name": node.name,
            "quoted": bool(node.args.get("quoted")),
        }
    if isinstance(node, exp.Column):
        return {"node": "column", "name": identifier(node)}
    return {
        "node": node.key,
        "args": {
            key: [
                expression(x, dialect) if isinstance(x, exp.Expression) else x
                for x in value
            ]
            if isinstance(value, list)
            else expression(value, dialect)
            if isinstance(value, (exp.Expression, Enum))
            else value
            for key, value in node.args.items()
            if value is not None
        },
    }


def normalized(node, dialect=None):
    from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

    if node is None:
        return None
    # SQLGlot handles dialect case folding, without altering quoted identifiers.
    return normalize_identifiers(node.copy(), dialect=dialect).sql(dialect=dialect)


def constraints(tree, table, dialect):
    result = []
    kinds = (
        exp.PrimaryKey,
        exp.PrimaryKeyColumnConstraint,
        exp.ForeignKey,
        exp.Reference,
        exp.UniqueColumnConstraint,
        exp.CheckColumnConstraint,
    )
    for node in tree.walk():
        if not isinstance(node, kinds):
            continue
        if isinstance(node, exp.Reference) and node.find_ancestor(exp.ForeignKey):
            continue
        column = node.find_ancestor(exp.ColumnDef)
        named = node.find_ancestor(exp.Constraint)
        wrapper = node.find_ancestor(exp.ColumnConstraint)
        cname = (
            identifier(named.this)
            if named
            else identifier(wrapper.this)
            if wrapper and wrapper.this
            else None
        )
        cols = [identifier(column.this)] if column else []
        data = {
            "table": table,
            "constraint_name": cname,
            "dialect": dialect or "generic",
        }
        if isinstance(node, (exp.PrimaryKey, exp.PrimaryKeyColumnConstraint)):
            data["constraint_type"] = "primary_key"
            cols = cols or [identifier(x) for x in node.expressions]
        elif isinstance(node, exp.UniqueColumnConstraint):
            data["constraint_type"] = "unique"
            cols = cols or [
                identifier(x) for x in (node.this.expressions if node.this else [])
            ]
        elif isinstance(node, exp.CheckColumnConstraint):
            data.update(
                constraint_type="check",
                expression=normalized(node.this, dialect),
                expression_ast=expression(node.this, dialect),
            )
            cols = list(
                dict.fromkeys(
                    identifier(x.this) for x in node.this.find_all(exp.Column)
                )
            )
        else:
            ref = node.args["reference"] if isinstance(node, exp.ForeignKey) else node
            target = ref.this
            data.update(
                constraint_type="foreign_key",
                target_table=identifier(
                    target.this if isinstance(target, exp.Schema) else target
                ),
                target_columns=[identifier(x) for x in target.expressions]
                if isinstance(target, exp.Schema)
                else [],
                options=ref.args.get("options") or [],
            )
            cols = cols or [identifier(x) for x in node.expressions]
        data["columns"] = cols
        data["constraint_id"] = (
            table + "." + cname if cname else uid("CONSTRAINT", data)
        )
        result.append(data)
    return result


def columns(tree, table, dialect):
    all_constraints = constraints(tree, table, dialect)
    result = []
    for col in tree.expressions:
        if not isinstance(col, exp.ColumnDef):
            continue
        name = identifier(col.this)
        declared = [c.kind for c in col.constraints]
        not_null = any(
            isinstance(c, exp.NotNullColumnConstraint) and not c.args.get("allow_null")
            for c in declared
        )
        explicit_null = any(
            isinstance(c, exp.NotNullColumnConstraint) and c.args.get("allow_null")
            for c in declared
        )
        pk = any(
            c["constraint_type"] == "primary_key" and name in c["columns"]
            for c in all_constraints
        )
        default = next(
            (c.this for c in declared if isinstance(c, exp.DefaultColumnConstraint)),
            None,
        )
        # SQLite's ordinary rowid tables allow NULL in many PRIMARY KEY columns.
        pk_not_null = pk and dialect in {"oracle", "postgres", "mysql", "tsql"}
        result.append(
            {
                "name": table + "." + name,
                "table": table,
                "column": name,
                "datatype": col.args["kind"].sql(dialect=dialect),
                "datatype_ast": expression(col.args["kind"], dialect),
                "nullable": False if not_null or pk_not_null else True,
                "nullability_declaration": "not_null"
                if not_null
                else "null"
                if explicit_null
                else "unspecified",
                "nullability_basis": "declared"
                if not_null or explicit_null
                else "primary_key"
                if pk_not_null
                else "dialect_default",
                "default": {
                    "present": default is not None,
                    "sql": normalized(default, dialect),
                    "expression_ast": expression(default, dialect),
                },
                "constraints": [c for c in all_constraints if name in c["columns"]],
                "dialect": dialect or "generic",
            }
        )
    return result


def statement(tree, owner, occurrence, dialect):
    target = tree.this
    if isinstance(target, exp.Schema):
        target = target.this
    table = identifier(target) if isinstance(target, exp.Table) else None
    data = {
        "owner": owner,
        "statement_type": tree.key,
        "dialect": dialect or "generic",
        "statement_id": uid("STMT", [owner, occurrence]),
        "target": table,
        "target_ast": expression(target, dialect)
        if isinstance(target, exp.Table)
        else None,
        "has_where": bool(tree.args.get("where")),
        "components": [],
    }
    parts = data["components"]

    def slot(key, entity, prop, value, **extra):
        parts.append(
            {
                "key": key,
                "entity": entity or data["statement_id"],
                "property": prop,
                "value": value,
                **extra,
            }
        )

    def assignment(lhs, rhs, key, branch=None, row=None):
        value = literal(rhs, dialect)
        col = identifier(lhs.this) if isinstance(lhs, exp.Column) else identifier(lhs)
        slot(
            key,
            (table + "." + col) if table else col,
            "assigned_value" if value is not None else "assignment_expression",
            value if value is not None else normalized(rhs, dialect),
            rhs_ast=expression(rhs, dialect),
            branch=branch,
            row=row,
            column=col,
        )

    def update(node, prefix="", branch=None):
        for i, assign in enumerate(node.expressions):
            if isinstance(assign, exp.EQ) and isinstance(assign.this, exp.Column):
                assignment(
                    assign.this, assign.expression, f"{prefix}assignment:{i}", branch
                )
            else:
                parts.append(
                    {
                        "key": f"{prefix}assignment:{i}",
                        "unsupported": "tuple_assignment",
                        "ast": expression(assign, dialect),
                    }
                )
        if node.args.get("where"):
            pred = node.args["where"].this
            slot(
                prefix + "where",
                table,
                "row_selection_expression",
                normalized(pred, dialect),
                expression_ast=expression(pred, dialect),
                branch=branch,
            )

    def insert(node, prefix="", branch=None):
        cols = (
            node.this.expressions
            if isinstance(node.this, (exp.Schema, exp.Tuple))
            else []
        )
        rhs = node.expression
        rows = rhs.expressions if isinstance(rhs, exp.Values) else [rhs]
        if not cols or not rows:
            parts.append(
                {"key": prefix + "mapping", "unsupported": "insert_implicit_columns"}
            )
            return
        for r, row in enumerate(rows):
            values = row.expressions if isinstance(row, (exp.Select, exp.Tuple)) else []
            if len(cols) != len(values) or any(v.is_star for v in values):
                parts.append(
                    {
                        "key": prefix + f"mapping:{r}",
                        "unsupported": "insert_projection_arity",
                    }
                )
                continue
            for i, (col, val) in enumerate(zip(cols, values)):
                rhs_value = val.this if isinstance(val, exp.Alias) else val
                assignment(col, rhs_value, f"{prefix}assignment:{r}:{i}", branch, r)

    if isinstance(tree, exp.Update):
        update(tree)
    elif isinstance(tree, exp.Insert):
        insert(tree)
    elif isinstance(tree, exp.Delete):
        if tree.args.get("where"):
            pred = tree.args["where"].this
            slot(
                "where",
                table,
                "row_selection_expression",
                normalized(pred, dialect),
                expression_ast=expression(pred, dialect),
            )
    elif isinstance(tree, exp.Merge):
        slot(
            "on",
            table,
            "merge_condition",
            normalized(tree.args["on"], dialect),
            expression_ast=expression(tree.args["on"], dialect),
        )
        data["source"] = expression(tree.args["using"], dialect)
        for i, branch in enumerate(tree.args["whens"].expressions):
            action = branch.args["then"]
            slot(
                f"branch:{i}",
                table,
                "merge_branch",
                expression(branch, dialect),
                branch=i,
            )
            if isinstance(action, exp.Update):
                update(action, f"branch:{i}:", i)
            elif isinstance(action, exp.Insert):
                insert(action, f"branch:{i}:", i)
    elif isinstance(tree, (exp.Select, exp.Union, exp.Except, exp.Intersect)):
        for i, query in enumerate(tree.find_all(exp.Select)):
            for j, projection in enumerate(query.expressions):
                slot(
                    f"projection:{i}:{j}",
                    None,
                    "projection",
                    expression(projection, dialect),
                    projection_sql=normalized(projection, dialect),
                )
    else:
        data["unsupported"] = "statement_outside_subset"
    return data
