"""Versioned P2d evaluator with runtime-checked deterministic temporal functions.

Only trusted local database *paths* belong here. This is defense in depth for
SQL, not an OS sandbox for hostile SQLite files. Result rows remain private.
Byte limits count UTF-8 column names/cells, blob bytes, eight bytes per number,
one byte per NULL, and eight bytes of framing per row. Temporal functions are
overridden by deterministic wrappers which reject runtime clock/timezone inputs.
"""
from __future__ import annotations

from collections import Counter
import math
import multiprocessing
from pathlib import Path
import pickle
import sqlite3
import tempfile
import time

import sqlglot
from sqlglot import exp
from sqlglot.dialects.sqlite import SQLite
from sqlglot.errors import ParseError


# SQLite's authorizer uses actual SQLite names, avoiding normalized AST aliases.
_FUNCTIONS = frozenset("""
abs avg ceil ceiling char coalesce concat concat_ws count cume_dist dense_rank
exp first_value floor format glob group_concat hex if ifnull iif instr json
json_array json_array_length json_error_position json_extract json_insert
json_object json_patch json_quote json_remove json_replace json_set json_type
json_valid json_group_array json_group_object lag last_value lead length like
likelihood likely ln log log10 log2 lower ltrim max min mod nth_value ntile
nullif percent_rank pi pow power printf quote rank replace round row_number
rtrim sign sin cos tan asin acos atan atan2 sinh cosh tanh asinh acosh atanh
sqrt string_agg substr substring sum total trim trunc typeof unhex unicode
unlikely upper zeroblob date time datetime julianday unixepoch strftime timediff
cast extract
""".split())
_TEMPORAL = frozenset({"date", "time", "datetime", "julianday", "unixepoch", "strftime", "timediff"})
_FORBIDDEN_NODES = frozenset("""
Insert Update Delete Create Drop Alter Merge Into Command Pragma Attach Detach
Transaction Commit Rollback Grant Revoke Use Set Execute Analyze Vacuum Cache
Uncache LoadData Copy TruncateTable Lock Unlock Kill Fetch Show Describe
""".split())
_QUERY_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)


def _literal_temporal_parser(name):
    return lambda args: exp.Anonymous(this=name, expressions=args)


class _LiteralTemporalSQLite(SQLite):
    """Keep temporal source arguments intact instead of normalizing strftime."""

    class Parser(SQLite.Parser):
        FUNCTIONS = {
            **SQLite.Parser.FUNCTIONS,
            **{name.upper(): _literal_temporal_parser(name) for name in _TEMPORAL},
        }


class _Blocked(Exception):
    pass


class _Budget(Exception):
    def __init__(self, status):
        self.status = status


def _validate_sql(sql):
    trees = sqlglot.parse(sql, read=_LiteralTemporalSQLite)
    trees = [tree for tree in trees if tree is not None]
    if len(trees) != 1 or not isinstance(trees[0], _QUERY_ROOTS):
        raise _Blocked
    for node in trees[0].walk():
        if type(node).__name__ in _FORBIDDEN_NODES or isinstance(node, (exp.DDL, exp.DML)):
            raise _Blocked
        if isinstance(node, exp.Func):
            name = node.name.lower() if isinstance(node, exp.Anonymous) else node.sql_name().lower()
            if isinstance(node, exp.Anonymous) and name not in _FUNCTIONS:
                raise _Blocked
            if name in {"current_date", "current_time", "current_timestamp", "current_datetime"}:
                raise _Blocked
            if name in _TEMPORAL:
                arguments = list(node.iter_expressions())
                minimum_arguments = 2 if name in {"strftime", "timediff"} else 1
                if len(arguments) < minimum_arguments:
                    raise _Blocked
                if name == "timediff" and len(arguments) != 2:
                    raise _Blocked


_CLOCK_WORDS = frozenset({"now", "localtime", "utc", "subsec", "subsecond"})


def _time_sensitive_arguments(name, arguments):
    """Return only evaluated arguments SQLite treats as time-values/modifiers."""
    if name == "strftime":
        return arguments[1:]  # format is not a time-value
    return arguments


def _runtime_unsafe_argument(name, arguments):
    for value in _time_sensitive_arguments(name, arguments):
        # SQLite coerces BLOBs to text for date functions; CAST(BLOB('now'))
        # can therefore read the wall clock. Embedded NUL can truncate a text
        # value in SQLite's C parser, so reject it conservatively as well.
        if isinstance(value, bytes) or isinstance(value, str) and (
            "\x00" in value or value.strip().casefold() in _CLOCK_WORDS
        ):
            return True
    return False


def _temporal_wrapper(name, helper_connection, unsafe_seen):
    """Evaluate SQLite's built-in date function on bound values only."""
    def wrapped(*arguments):
        if _runtime_unsafe_argument(name, arguments):
            unsafe_seen.append(name)
            # The parent result maps this private control-flow exception to
            # blocked/unknown; no clock-aware SQLite date function is invoked.
            raise sqlite3.OperationalError("P2D_V2_BLOCKED_RUNTIME_CLOCK_ARGUMENT")
        placeholders = ",".join("?" for _ in arguments)
        return helper_connection.execute(
            f"SELECT {name}({placeholders})", tuple(arguments)
        ).fetchone()[0]
    return wrapped


def _sqlite_error_category(error):
    message = str(error).casefold()
    if "unsafe use of" in message:
        return "unsafe_schema_function"
    if "on clause references tables to its right" in message:
        return "bad_join"
    if "no such table:" in message:
        return "missing_table"
    if "ambiguous column name:" in message:
        return "ambiguous_column"
    if "no such column:" in message:
        return "missing_column"
    if "datatype mismatch" in message:
        return "datatype"
    if "no such function:" in message or "wrong number of arguments to function" in message:
        return "unsupported_func"
    return "other"


def _authorize(action, first, second, database, trigger):
    if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (second or first or "").lower() in _FUNCTIONS:
        # Stored views are not part of the parsed query. Their temporal
        # arguments cannot be verified, so deny them conservatively.
        if trigger is not None and (second or first or "").lower() in _TEMPORAL:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _cell_bytes(value):
    if value is None:
        return 1
    if isinstance(value, (int, float)):
        return 8
    if isinstance(value, bytes):
        return len(value)
    return len(value.encode("utf-8"))


def _set_sqlite_memory_limit(conn, requested):
    """Fail closed unless SQLite confirms a positive effective hard heap cap."""
    row = conn.execute(f"PRAGMA hard_heap_limit={requested}").fetchone()
    if not row or not isinstance(row[0], int) or not 0 < row[0] <= requested:
        raise _Budget("memory_limit")
    return row[0]


def _worker(db_path, sql, row_limit, byte_limit, sqlite_memory_limit, output_path):
    result = {"status": "error", "error_type": "worker_error"}
    conn = None
    helper_connection = None
    unsafe_temporal = []
    length_limit_status = "byte_limit"
    try:
        _validate_sql(sql)
        uri = Path(db_path).resolve().as_uri() + "?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True, timeout=0)
        helper_connection = sqlite3.connect(":memory:")
        effective_memory_limit = _set_sqlite_memory_limit(conn, sqlite_memory_limit)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA trusted_schema=OFF")
        # Bound individual cell allocation before Python receives a large value.
        if effective_memory_limit // 2 < byte_limit:
            length_limit_status = "memory_limit"
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, max(1024, min(byte_limit, effective_memory_limit // 2, 2**31 - 1)))
        conn.set_authorizer(_authorize)
        for function_name in _TEMPORAL:
            conn.create_function(
                function_name,
                -1,
                _temporal_wrapper(function_name, helper_connection, unsafe_temporal),
                deterministic=True,
            )
        cursor = conn.execute(sql)
        columns = [item[0] for item in cursor.description]
        size = sum(len(column.encode("utf-8")) for column in columns)
        if size > byte_limit:
            raise _Budget("byte_limit")
        rows = []
        for row in cursor:
            if len(rows) >= row_limit:
                raise _Budget("row_limit")
            size += 8 + sum(_cell_bytes(value) for value in row)
            if size > byte_limit:
                raise _Budget("byte_limit")
            rows.append(row)
        result = {"status": "ok", "rows": rows, "columns": columns}
    except _Blocked:
        result = {"status": "blocked", "error_type": "unsafe_sql"}
    except _Budget as exc:
        result = {"status": exc.status, "error_type": exc.status}
    except ParseError:
        result = {"status": "error", "error_type": "sql_parse_error"}
    except MemoryError:
        result = {"status": "memory_limit", "error_type": "sqlite_memory_limit"}
    except sqlite3.Error as exc:
        if unsafe_temporal:
            result = {"status": "blocked", "error_type": "temporal_runtime_unsafe_argument"}
        elif getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_NOMEM:
            result = {"status": "memory_limit", "error_type": "sqlite_memory_limit"}
        elif getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_TOOBIG:
            result = {"status": length_limit_status, "error_type": length_limit_status}
        elif "not authorized" in str(exc).lower() or getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_AUTH:
            result = {"status": "blocked", "error_type": "sqlite_authorizer_denied"}
        elif _sqlite_error_category(exc) == "unsafe_schema_function":
            result = {"status": "blocked", "error_type": "sqlite_authorizer_denied"}
        else:
            result = {
                "status": "error",
                "error_type": "sqlite_error",
                "error_category": _sqlite_error_category(exc),
            }
    except Exception:
        result = {"status": "error", "error_type": "worker_error"}
    finally:
        if helper_connection is not None:
            helper_connection.close()
        if conn is not None:
            conn.close()
    # A local temporary result file avoids pipe-buffer deadlocks when the parent
    # waits for worker completion. Only this process produces its pickle bytes.
    with open(output_path, "wb") as handle:
        pickle.dump(result, handle, protocol=pickle.HIGHEST_PROTOCOL)


def execute_readonly(db_path, sql, timeout=10, row_limit=50000, byte_limit=64 * 1024 * 1024,
                     sqlite_memory_limit=256 * 1024 * 1024):
    """Run one SELECT in an isolated, reaped worker, bounded by wall-clock time.

    Success: status, rows (list of tuples), columns, seconds. Other outcomes:
    status, seconds, error_type only. No SQL, path, or partial results in errors.
    The timeout includes validation/execution/result serialization, starting
    before worker creation; process termination and parent deserialization add
    small cleanup overhead. ``immutable`` requires a quiescent database snapshot.
    SQLite's process-local hard heap cap bounds SQLite working memory, including
    in-memory sorting/CTEs. Python parser/row/pickle allocations are outside
    SQLite's allocator; result rows remain bounded by row/byte caps.
    """
    start = time.monotonic()
    failure = lambda status, error: {"status": status, "seconds": time.monotonic() - start, "error_type": error}
    if (not isinstance(sql, str) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0
            or type(row_limit) is not int or row_limit < 0
            or type(byte_limit) is not int or byte_limit <= 0
            or type(sqlite_memory_limit) is not int or not 0 < sqlite_memory_limit <= 2**63 - 1):
        return failure("error", "invalid_arguments")
    process = None
    try:
        context = multiprocessing.get_context("fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn")
        with tempfile.TemporaryDirectory(prefix="p2d_sql_eval_") as directory:
            output_path = str(Path(directory) / "result.pickle")
            process = context.Process(target=_worker, args=(str(db_path), sql, row_limit, byte_limit, sqlite_memory_limit, output_path))
            process.start()
            process.join(max(0, timeout - (time.monotonic() - start)))
            if process.is_alive():
                return failure("timeout", "deadline_exceeded")
            if process.exitcode != 0 or not Path(output_path).is_file():
                return failure("error", "worker_exit")
            with open(output_path, "rb") as handle:
                result = pickle.load(handle)
            result["seconds"] = time.monotonic() - start
            return result
    except Exception:
        return failure("error", "worker_error")
    finally:
        if process is not None and process.pid is not None:
            if process.is_alive():
                process.terminate()
                process.join(0.2)
            if process.is_alive():
                process.kill()
            process.join()
            process.close()


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _row_matches(left, right):
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if _numeric(a) and _numeric(b):
            if a == b:
                continue
            if isinstance(a, int) or isinstance(b, int):
                return False
            try:
                if math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-8):
                    continue
            except OverflowError:
                pass
            return False
        if type(a) is not type(b) or a != b:
            return False
    return True


def _bag_matches(adjacency, right_count):
    if len(adjacency) != right_count:
        return False
    matched = {}

    def augment(left, seen):
        for right in adjacency[left]:
            if right in seen:
                continue
            seen.add(right)
            if right not in matched or augment(matched[right], seen):
                matched[right] = left
                return True
        return False

    return all(augment(left, set()) for left in range(len(adjacency)))


def compare_rows(predicted_rows, reference_rows):
    """Compare unordered rows with Set and Bag semantics and fixed column order.

    Integer-involving comparisons require equality (1 == 1.0); float/float
    values use rel_tol=1e-6, abs_tol=1e-8; strings/NULL are exact.
    Nonfinite/unsupported values and >500-row nonexact comparisons are
    unknown. Set comparison uses symmetric tolerance coverage, while Bag uses
    a true bipartite perfect matching (tolerance need not be transitive).
    """
    unknown = lambda reason: {"set_correct": None, "bag_correct": None, "comparison_status": reason}
    try:
        predicted = [tuple(row) for row in predicted_rows]
        reference = [tuple(row) for row in reference_rows]
    except (TypeError, ValueError):
        return unknown("unknown_invalid_rows")
    for row in predicted + reference:
        for value in row:
            if isinstance(value, float) and not math.isfinite(value):
                return unknown("unknown_nonfinite")
            if value is not None and type(value) not in {int, float, str, bytes}:
                return unknown("unknown_unsupported_type")
    left, right = Counter(predicted), Counter(reference)
    if left == right:
        return {"set_correct": True, "bag_correct": True, "comparison_status": "ok"}
    if not predicted or not reference:
        return {"set_correct": False, "bag_correct": False, "comparison_status": "ok"}
    exact_set = left.keys() == right.keys()
    if max(len(predicted), len(reference)) > 500:
        if exact_set:
            return {"set_correct": True, "bag_correct": None, "comparison_status": "unknown_large_nonexact"}
        return unknown("unknown_large_nonexact")
    adjacency = [[j for j, other in enumerate(reference) if _row_matches(row, other)] for row in predicted]
    covered = set(j for neighbors in adjacency for j in neighbors)
    set_correct = all(adjacency) and len(covered) == len(reference)
    bag_correct = set_correct and _bag_matches(adjacency, len(reference))
    return {"set_correct": bool(set_correct), "bag_correct": bool(bag_correct), "comparison_status": "ok"}
