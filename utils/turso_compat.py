import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    import libsql  # type: ignore
    HAS_LIBSQL = True
except ImportError:
    libsql = None
    HAS_LIBSQL = False


class DictRow:
    """Row adapter tương thích với sqlite3.Row (hỗ trợ cả row['col'], row[0], row.keys(), dict(row))."""

    def __init__(self, columns: Iterable[str], values: Iterable[Any]):
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._mapping = dict(zip(self._columns, self._values))

    def keys(self) -> list[str]:
        return list(self._columns)

    def get(self, key: str, default: Any = None) -> Any:
        return self._mapping.get(key, default)

    def __getitem__(self, key: int | slice | str) -> Any:
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._mapping[key]

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __repr__(self) -> str:
        return f"DictRow({self._mapping!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DictRow):
            return self._values == other._values and self._columns == other._columns
        if isinstance(other, tuple):
            return self._values == other
        return False


def _split_sql_statements(sql_script: str) -> list[str]:
    """Tách chuỗi SQL thành từng câu lệnh riêng, tôn trọng chuỗi trích dẫn và comment '--'."""
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    i = 0
    length = len(sql_script)

    while i < length:
        ch = sql_script[i]
        nxt = sql_script[i + 1] if i + 1 < length else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                current.append(ch)
            i += 1
            continue

        if not in_single_quote and not in_double_quote:
            if ch == "-" and nxt == "-":
                in_line_comment = True
                i += 2
                continue
            if ch == "'":
                in_single_quote = True
            elif ch == '"':
                in_double_quote = True
            elif ch == ";":
                stmt = "".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
                i += 1
                continue
        elif in_single_quote:
            if ch == "'" and nxt == "'":
                current.append("''")
                i += 2
                continue
            if ch == "'":
                in_single_quote = False
        elif in_double_quote:
            if ch == '"' and nxt == '"':
                current.append('""')
                i += 2
                continue
            if ch == '"':
                in_double_quote = False

        current.append(ch)
        i += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)

    return statements


class CompatCursor:
    """Cursor wrapper chuẩn hóa row_factory giữa sqlite3 và libsql."""

    def __init__(self, cursor: Any, conn_wrapper: "CompatConnection"):
        self._cursor = cursor
        self._conn_wrapper = conn_wrapper

    def _convert_row(self, row: Any) -> Any:
        if row is None:
            return None
        factory = self._conn_wrapper.row_factory
        if factory is None:
            return tuple(row) if not isinstance(row, tuple) else row
        if factory is sqlite3.Row:
            if isinstance(row, sqlite3.Row):
                return row
            cols = [col[0] for col in (self._cursor.description or ())]
            return DictRow(cols, row)
        if isinstance(row, (sqlite3.Row, DictRow)):
            raw_tuple = tuple(row)
        else:
            raw_tuple = row
        return factory(self._cursor, raw_tuple)

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> "CompatCursor":
        if parameters:
            self._cursor.execute(sql, tuple(parameters))
        else:
            self._cursor.execute(sql)
        return self

    def executemany(self, sql: str, seq_of_parameters: Iterable[Iterable[Any]]) -> "CompatCursor":
        self._cursor.executemany(sql, seq_of_parameters)
        return self

    def executescript(self, sql_script: str) -> "CompatCursor":
        self._conn_wrapper.executescript(sql_script)
        return self

    def fetchone(self) -> Any:
        return self._convert_row(self._cursor.fetchone())

    def fetchall(self) -> list[Any]:
        return [self._convert_row(r) for r in self._cursor.fetchall()]

    def fetchmany(self, size: int = 1) -> list[Any]:
        return [self._convert_row(r) for r in self._cursor.fetchmany(size)]

    def close(self) -> None:
        self._cursor.close()

    @property
    def description(self):
        return self._cursor.description

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def arraysize(self):
        return self._cursor.arraysize

    @arraysize.setter
    def arraysize(self, value: int) -> None:
        self._cursor.arraysize = value

    def __iter__(self):
        for row in self._cursor:
            yield self._convert_row(row)


class CompatConnection:
    """Connection wrapper cung cấp API đồng nhất cho cả sqlite3 cục bộ và Turso libsql."""

    def __init__(
        self,
        conn: Any,
        is_remote: bool = False,
        row_factory: Optional[Callable[..., Any]] = None,
    ):
        self._conn = conn
        self.is_remote = is_remote
        self.row_factory = row_factory

    def cursor(self) -> CompatCursor:
        return CompatCursor(self._conn.cursor(), self)

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> CompatCursor:
        cur = self.cursor()
        return cur.execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Iterable[Iterable[Any]]) -> CompatCursor:
        cur = self.cursor()
        return cur.executemany(sql, seq_of_parameters)

    def executescript(self, sql_script: str) -> None:
        if not self.is_remote and hasattr(self._conn, "executescript"):
            self._conn.executescript(sql_script)
            return
        for stmt in _split_sql_statements(sql_script):
            self._conn.execute(stmt)
        self._conn.commit()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "CompatConnection":
        if hasattr(self._conn, "__enter__"):
            self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Any:
        if hasattr(self._conn, "__exit__"):
            return self._conn.__exit__(exc_type, exc_val, exc_tb)
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


def is_turso_configured(url_env: str) -> bool:
    return bool(os.getenv(url_env, "").strip())


def open_connection(
    local_path: Path | str,
    url_env: str,
    token_env: str,
    row_factory: Optional[Callable[..., Any]] = None,
) -> CompatConnection:
    """
    Mở kết nối tới Turso nếu biến môi trường `url_env` được cấu hình,
    ngược lại fallback về SQLite cục bộ tại `local_path`.
    """
    turso_url = os.getenv(url_env, "").strip()
    if turso_url:
        if not HAS_LIBSQL:
            raise ImportError(
                f"Đã cấu hình {url_env} nhưng chưa cài thư viện 'libsql'. Hãy chạy: pip install libsql"
            )
        auth_token = os.getenv(token_env, "").strip()
        if not auth_token:
            raise ValueError(
                f"Đã cấu hình {url_env} nhưng thiếu {token_env}. Vui lòng bổ sung auth token của Turso."
            )
        conn = libsql.connect(turso_url, auth_token=auth_token)
        return CompatConnection(conn, is_remote=True, row_factory=row_factory)

    conn = sqlite3.connect(str(local_path))
    return CompatConnection(conn, is_remote=False, row_factory=row_factory)

