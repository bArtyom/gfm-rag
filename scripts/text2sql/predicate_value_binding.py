"""Conservative direct predicate-to-base-column binding for an offline audit."""
from collections import Counter
import hashlib

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope

from scripts.text2sql.audit_p2c_values_risk import normalize


def _eligible_literals(tree):
    for literal in tree.find_all(exp.Literal):
        if literal.find_ancestor(exp.Limit, exp.Offset) is not None:
            continue
        predicate = literal.find_ancestor(exp.Predicate)
        if predicate is None or predicate.find(exp.Column) is None:
            continue
        parent, negatives = literal.parent, 0
        while parent is not predicate and isinstance(parent, (exp.Neg, exp.Paren, exp.Tuple)):
            negatives += int(isinstance(parent, exp.Neg))
            parent = parent.parent
        if parent is not predicate:
            continue
        value = normalize(('-' if negatives % 2 else '') + str(literal.this))
        if not value or (literal.is_string and isinstance(predicate, (exp.Like, exp.ILike, exp.RegexpLike)) and any(c in value for c in '%_')):
            continue
        kind = 'string' if literal.is_string else 'number'
        key = hashlib.sha256(f'{kind}:{value}'.encode()).hexdigest()
        yield literal, predicate, key


def _strip_parens(expression):
    while isinstance(expression, exp.Paren):
        expression = expression.this
    return expression


def _contains(expression, literal):
    return expression is not None and any(node is literal for node in expression.walk())


def _predicate_target(predicate, literal):
    if isinstance(predicate, exp.In):
        return predicate.this if any(_contains(item, literal) for item in predicate.expressions) else None
    if isinstance(predicate, exp.Between):
        return predicate.this if any(_contains(predicate.args.get(key), literal) for key in ('low', 'high')) else None
    if isinstance(predicate, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Like, exp.ILike, exp.RegexpLike, exp.Is)):
        if _contains(predicate.this, literal):
            return predicate.expression
        if _contains(predicate.expression, literal):
            return predicate.this
    return None


def _resolve_column(column, scope, catalog, visited=None):
    visited = set() if visited is None else visited
    identity = (id(scope), column.table.casefold(), column.name.casefold())
    if identity in visited or len(visited) > 100:
        return None, 'recursive_or_deep_lineage'
    visited.add(identity)
    alias = column.table.casefold()
    sources = {name.casefold(): source for name, (_, source) in scope.selected_sources.items()}
    if alias not in sources:
        if scope.parent is not None and scope.can_be_correlated:
            return _resolve_column(column, scope.parent, catalog, visited)
        return None, 'unknown_source'
    source = sources[alias]
    if isinstance(source, exp.Table):
        if source.db.casefold() not in ('', 'main') or source.catalog:
            return None, 'external_database_source'
        node = catalog.get(source.name.casefold(), {}).get(column.name.casefold())
        return (node, None) if node else (None, 'unknown_base_column')
    if not isinstance(source, Scope) or not isinstance(source.expression, exp.Select):
        return None, 'unsupported_source_or_union'
    projections = [item for item in source.expression.expressions if item.alias_or_name.casefold() == column.name.casefold()]
    if len(projections) != 1:
        return None, 'ambiguous_or_missing_derived_projection'
    projection = projections[0]
    if isinstance(projection, exp.Alias):
        projection = projection.this
    projection = _strip_parens(projection)
    if not isinstance(projection, exp.Column):
        return None, 'computed_derived_projection'
    return _resolve_column(projection, source, catalog, visited)


def bind_sql_literals(sql, schema_columns):
    """Return only literal hashes, base node IDs and explicit unknown reasons.

    A supported binding proves AST incidence, not business necessity. Whole-query
    qualification errors are retained as unknown; ambiguous names are never guessed.
    """
    tree = sqlglot.parse_one(sql, read='sqlite')
    originals = list(_eligible_literals(tree))
    counts = Counter(key for _, _, key in originals)
    result = {key: {'node_ids': set(), 'unresolved_reasons': set(), 'occurrences': count} for key, count in counts.items()}
    for index, (literal, _, _) in enumerate(originals):
        literal.meta['value_binding_audit_ordinal'] = index
    catalog = {table.casefold(): {column.casefold(): node for column, node in columns.items()} for table, columns in schema_columns.items()}
    schema = {table: {column: 'UNKNOWN' for column in columns} for table, columns in catalog.items()}
    try:
        qualified = qualify(tree, dialect='sqlite', schema=schema, infer_schema=False, expand_stars=False,
                            quote_identifiers=False, identify=False, validate_qualify_columns=True)
    except sqlglot.errors.OptimizeError:
        for value in result.values():
            value['unresolved_reasons'].add('qualification_error')
    else:
        scopes = {id(scope.expression): scope for scope in traverse_scope(qualified)}
        observed = set()
        for literal, predicate, key in _eligible_literals(qualified):
            ordinal = literal.meta.get('value_binding_audit_ordinal')
            if ordinal is None or ordinal >= len(originals) or originals[ordinal][2] != key:
                continue
            observed.add(ordinal)
            target = _strip_parens(_predicate_target(predicate, literal))
            scope = scopes.get(id(literal.find_ancestor(exp.Select)))
            if not isinstance(target, exp.Column):
                node, reason = None, 'transformed_or_unsupported_predicate_target'
            elif scope is None:
                node, reason = None, 'missing_select_scope'
            else:
                node, reason = _resolve_column(target, scope, catalog)
            if node:
                result[key]['node_ids'].add(node)
            if reason:
                result[key]['unresolved_reasons'].add(reason)
        for index, (_, _, key) in enumerate(originals):
            if index not in observed:
                result[key]['unresolved_reasons'].add('literal_not_preserved_after_qualification')
    return {key: {**value, 'node_ids': sorted(value['node_ids']), 'unresolved_reasons': sorted(value['unresolved_reasons'])} for key, value in result.items()}


def classify_binding(binding, matching_node_ids):
    if set(binding['node_ids']).intersection(matching_node_ids):
        return 'binding_supported'
    if binding['unresolved_reasons'] or not binding['node_ids']:
        return 'binding_unresolved'
    return 'binding_mismatch'
