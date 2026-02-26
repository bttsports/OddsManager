"""
Small API for the X list monitor: POST new tweets (from Tampermonkey) and GET recent tweets (for the app).
Run from repo root: python news/tweets_api.py
Default: http://localhost:8765

Endpoints: GET /health (liveness, no DB), GET /api/tweets, POST /api/tweet, POST /api/tweet/into/<table>, etc.
If the server won't start, run in a terminal from repo root and check stderr (MySQL, os_check, settings_win).
"""
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from os_check import USER, PASSWORD, HOST

# Import db only inside request handlers so no MySQL connection is created in the main thread.
# (mysql.connector can raise "Connection not available" when a connection is used from another thread.)

app = Flask(__name__)
CORS(app)


@app.route("/health", methods=["GET"])
def health():
    """Lightweight liveness check; does not touch MySQL. Use for 'is the server up?'."""
    return jsonify({"ok": True}), 200


def _connect():
    """New connection every time; mysql.connector connections must not be shared across threads."""
    return mysql.connector.connect(
        user=USER, password=PASSWORD, host=HOST, database="news_sources"
    )


@app.route("/api/tables", methods=["GET"])
def get_tables():
    """Returns list of table names in news_sources (for dropdown)."""
    try:
        import db
        conn = _connect()
        try:
            tables = db.list_tables(conn)
            return jsonify({"ok": True, "tables": sorted(tables)})
        finally:
            conn.close()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "error": err}), 500


@app.route("/api/tweet/into/<table_name>", methods=["POST"])
def post_tweet_into(table_name):
    """Body: JSON { tweet_id, author_handle, text, url?, posted_at? }. Inserts into the given table (must exist in news_sources)."""
    import re
    if not re.match(r"^[a-z][a-z0-9_]*$", table_name):
        return jsonify({"ok": False, "error": "Invalid table name"}), 400
    data = request.get_json(force=True, silent=True) or {}
    tweet_id = data.get("tweet_id") or ""
    author_handle = (data.get("author_handle") or "unknown").lstrip("@")
    text = data.get("text") or ""
    url = data.get("url")
    posted_at = data.get("posted_at")
    if not tweet_id or not text:
        return jsonify({"ok": False, "error": "tweet_id and text required"}), 400
    try:
        import db
        conn = _connect()
        try:
            allowed = db.list_tables(conn)
            if table_name not in allowed:
                return jsonify({"ok": False, "error": f"Table {table_name} not found in news_sources"}), 404
            db.insert_tweet_into_table(conn, table_name, tweet_id, author_handle, text, url, posted_at)
            return jsonify({"ok": True})
        finally:
            conn.close()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "error": err}), 500


@app.route("/api/tweet", methods=["POST"])
def post_tweet():
    """Body: JSON { tweet_id, author_handle, text, url?, posted_at? }. Inserts into mlb_tweets."""
    data = request.get_json(force=True, silent=True) or {}
    tweet_id = data.get("tweet_id") or ""
    author_handle = (data.get("author_handle") or "unknown").lstrip("@")
    text = data.get("text") or ""
    url = data.get("url")
    posted_at = data.get("posted_at")
    if not tweet_id or not text:
        return jsonify({"ok": False, "error": "tweet_id and text required"}), 400
    try:
        import db
        conn = _connect()
        try:
            db.insert_mlb_tweet(conn, tweet_id, author_handle, text, url, posted_at)
            return jsonify({"ok": True})
        finally:
            conn.close()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "error": err}), 500

@app.route("/api/tweet/golf", methods=["POST"])
def post_tweet_golf():
    """Body: JSON { tweet_id, author_handle, text, url?, posted_at? }. Inserts into golf_tweets."""
    data = request.get_json(force=True, silent=True) or {}
    tweet_id = data.get("tweet_id") or ""
    author_handle = (data.get("author_handle") or "unknown").lstrip("@")
    text = data.get("text") or ""
    url = data.get("url")
    posted_at = data.get("posted_at")
    if not tweet_id or not text:
        return jsonify({"ok": False, "error": "tweet_id and text required"}), 400
    try:
        import db
        conn = _connect()
        try:
            db.insert_golf_tweet(conn, tweet_id, author_handle, text, url, posted_at)
            return jsonify({"ok": True})
        finally:
            conn.close()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "error": err}), 500


@app.route("/api/tweet/all", methods=["POST"])
def post_tweet_all():
    """Body: JSON { tweet_id, author_handle, text, url?, posted_at? }. Inserts into mlb_tweets_all."""
    data = request.get_json(force=True, silent=True) or {}
    tweet_id = data.get("tweet_id") or ""
    author_handle = (data.get("author_handle") or "unknown").lstrip("@")
    text = data.get("text") or ""
    url = data.get("url")
    posted_at = data.get("posted_at")
    if not tweet_id or not text:
        return jsonify({"ok": False, "error": "tweet_id and text required"}), 400
    try:
        import db
        conn = _connect()
        try:
            db.insert_mlb_tweet_all(conn, tweet_id, author_handle, text, url, posted_at)
            return jsonify({"ok": True})
        finally:
            conn.close()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "error": err}), 500


@app.route("/api/tweets", methods=["GET"])
def get_tweets():
    """Query params: limit (default 100). Returns recent tweets from mlb_tweets (newest first)."""
    limit = min(500, max(1, int(request.args.get("limit", 100))))
    try:
        import db
        conn = _connect()
        try:
            cursor = conn.cursor(buffered=True)
            cursor.execute(
                "SELECT id, tweet_id, author_handle, text, url, posted_at, inserted_at "
                "FROM mlb_tweets ORDER BY inserted_at DESC LIMIT %s",
                (limit,),
            )
            rows = db.fetchall_named(cursor)
            cursor.close()
            for r in rows:
                if r.get("posted_at"):
                    r["posted_at"] = r["posted_at"].isoformat() if hasattr(r["posted_at"], "isoformat") else str(r["posted_at"])
                if r.get("inserted_at"):
                    r["inserted_at"] = r["inserted_at"].isoformat() if hasattr(r["inserted_at"], "isoformat") else str(r["inserted_at"])
            return jsonify({"ok": True, "tweets": rows})
        finally:
            conn.close()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "error": err}), 500


def _get_tweets_from_table(table, limit):
    import db
    conn = _connect()
    try:
        cursor = conn.cursor(buffered=True)
        cursor.execute(
            "SELECT id, tweet_id, author_handle, text, url, posted_at, inserted_at "
            "FROM " + table + " ORDER BY inserted_at DESC LIMIT %s",
            (limit,),
        )
        rows = db.fetchall_named(cursor)
        cursor.close()
        for r in rows:
            if r.get("posted_at"):
                r["posted_at"] = r["posted_at"].isoformat() if hasattr(r["posted_at"], "isoformat") else str(r["posted_at"])
            if r.get("inserted_at"):
                r["inserted_at"] = r["inserted_at"].isoformat() if hasattr(r["inserted_at"], "isoformat") else str(r["inserted_at"])
        return jsonify({"ok": True, "tweets": rows})
    finally:
        conn.close()


@app.route("/api/tweets/all", methods=["GET"])
def get_tweets_all():
    """Query params: limit (default 100). Returns recent tweets from mlb_tweets_all (newest first)."""
    limit = min(500, max(1, int(request.args.get("limit", 100))))
    try:
        return _get_tweets_from_table("mlb_tweets_all", limit)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "error": err}), 500


@app.route("/api/tweets/golf", methods=["GET"])
def get_tweets_golf():
    """Query params: limit (default 100). Returns recent tweets from golf_tweets (newest first)."""
    limit = min(500, max(1, int(request.args.get("limit", 100))))
    try:
        return _get_tweets_from_table("golf_tweets", limit)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "error": err}), 500


# Allowed table name: lowercase letters, digits, underscore only; must end with _tweets.
import re
_CREATE_TABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*_tweets$")


@app.route("/api/create-table", methods=["POST"])
def create_table():
    """Body: JSON { table_name: "my_monitor_tweets" }. Creates table in news_sources with same schema as mlb_tweets."""
    data = request.get_json(force=True, silent=True) or {}
    table_name = (data.get("table_name") or "").strip()
    if not table_name:
        return jsonify({"ok": False, "error": "table_name required"}), 400
    if not _CREATE_TABLE_NAME_RE.match(table_name):
        return jsonify({
            "ok": False,
            "error": "table_name must be lowercase, alphanumeric + underscore, and end with _tweets (e.g. mlb_news_tweets)"
        }), 400
    try:
        import db
        conn = _connect()
        try:
            db.create_tweets_table(conn, table_name)
            return jsonify({"ok": True, "table_name": table_name})
        finally:
            conn.close()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "error": err}), 500


if __name__ == "__main__":
    # Log whether DB is reachable at startup (helps debug when run by Tauri vs shell).
    try:
        c = mysql.connector.connect(user=USER, password=PASSWORD, host=HOST, database="news_sources")
        c.close()
        print("MySQL news_sources OK", file=sys.stderr)
    except Exception as e:
        print("MySQL at startup:", e, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    app.run(host="0.0.0.0", port=8765, debug=False)
