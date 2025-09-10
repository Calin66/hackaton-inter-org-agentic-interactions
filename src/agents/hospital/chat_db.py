import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    create_engine,
    text,
)

# SQLite file lives under project data/
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DATA_DIR = os.path.abspath(DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
SQLITE_PATH = os.path.join(DATA_DIR, "app.sqlite3")

# Note: check_same_thread disabled implicitly by SQLAlchemy; safer to use pysqlite driver
engine = create_engine(f"sqlite:///{SQLITE_PATH}", future=True)


def _utcnow() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def init_db():
    """Create tables if they don't exist."""
    with engine.begin() as conn:
        # Ensure foreign keys ON
        conn.execute(text("PRAGMA foreign_keys=ON"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    insurance_status TEXT CHECK(insurance_status IN ('pending','approved','denied')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    tool_result TEXT,
                    status TEXT CHECK(status IN ('pending','approved','denied')),
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                )
                """
            )
        )


def create_chat(chat_id: str, title: str, insurance_status: Optional[str] = None) -> Dict[str, Any]:
    now = _utcnow()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO chats (id, title, insurance_status, created_at, updated_at)
                VALUES (:id, :title, :st, :now, :now)
                ON CONFLICT(id) DO NOTHING
                """
            ),
            {"id": chat_id, "title": title, "st": insurance_status, "now": now},
        )
        row = conn.execute(text("SELECT id, title, insurance_status, created_at, updated_at FROM chats WHERE id=:id"), {"id": chat_id}).mappings().first()
    return dict(row) if row else {"id": chat_id, "title": title, "insurance_status": insurance_status, "created_at": now, "updated_at": now}


def list_chats() -> List[Dict[str, Any]]:
    with engine.begin() as conn:
        res = conn.execute(
            text(
                "SELECT id, title, insurance_status, created_at, updated_at FROM chats ORDER BY updated_at DESC, created_at DESC"
            )
        ).mappings().all()
        return [dict(r) for r in res]


def get_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, title, insurance_status, created_at, updated_at FROM chats WHERE id=:id"),
            {"id": chat_id},
        ).mappings().first()
        return dict(row) if row else None


def update_chat(chat_id: str, *, title: Optional[str] = None, insurance_status: Optional[str] = None) -> Optional[Dict[str, Any]]:
    sets = []
    params: Dict[str, Any] = {"id": chat_id, "now": _utcnow()}
    if title is not None:
        sets.append("title=:title")
        params["title"] = title
    if insurance_status is not None:
        sets.append("insurance_status=:st")
        params["st"] = insurance_status
    if not sets:
        return get_chat(chat_id)
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE chats SET {', '.join(sets)}, updated_at=:now WHERE id=:id"), params)
        row = conn.execute(text("SELECT id, title, insurance_status, created_at, updated_at FROM chats WHERE id=:id"), {"id": chat_id}).mappings().first()
        return dict(row) if row else None


def delete_chat(chat_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("DELETE FROM messages WHERE chat_id=:id"), {"id": chat_id})
        conn.execute(text("DELETE FROM chats WHERE id=:id"), {"id": chat_id})


def add_message(
    *,
    id: str,
    chat_id: str,
    role: str,
    content: str,
    tool_result: Optional[Dict[str, Any]] = None,
    status: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    created_at = created_at or _utcnow()
    tool_str = json.dumps(tool_result, ensure_ascii=False) if tool_result is not None else None
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO messages (id, chat_id, role, content, tool_result, status, created_at)
                VALUES (:id, :chat_id, :role, :content, :tool, :status, :ts)
                ON CONFLICT(id) DO NOTHING
                """
            ),
            {
                "id": id,
                "chat_id": chat_id,
                "role": role,
                "content": content,
                "tool": tool_str,
                "status": status,
                "ts": created_at,
            },
        )
        # Touch chat updated_at
        conn.execute(text("UPDATE chats SET updated_at=:now WHERE id=:id"), {"id": chat_id, "now": _utcnow()})
        row = conn.execute(text("SELECT id, chat_id, role, content, tool_result, status, created_at FROM messages WHERE id=:id"), {"id": id}).mappings().first()
    out = dict(row or {})
    if out.get("tool_result"):
        try:
            out["tool_result"] = json.loads(out["tool_result"]) if isinstance(out["tool_result"], str) else out["tool_result"]
        except Exception:
            pass
    return out


def list_messages(chat_id: str) -> List[Dict[str, Any]]:
    with engine.begin() as conn:
        res = conn.execute(
            text(
                "SELECT id, chat_id, role, content, tool_result, status, created_at FROM messages WHERE chat_id=:id ORDER BY created_at ASC"
            ),
            {"id": chat_id},
        ).mappings().all()
    out: List[Dict[str, Any]] = []
    for r in res:
        item = dict(r)
        if item.get("tool_result"):
            try:
                item["tool_result"] = json.loads(item["tool_result"]) if isinstance(item["tool_result"], str) else item["tool_result"]
            except Exception:
                pass
        out.append(item)
    return out
