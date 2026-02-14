"""
Small API for the X list monitor: POST new tweets (from Tampermonkey) and GET recent tweets (for the app).
Run from repo root: python news/tweets_api.py
Default: http://localhost:8765
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, request, jsonify
from flask_cors import CORS
import db
from os_check import USER, PASSWORD, HOST

app = Flask(__name__)
CORS(app)

def get_db():
    try:
        return db.DBS["news_sources"]
    except KeyError:
        import mysql.connector
        return mysql.connector.connect(
            user=USER, password=PASSWORD, host=HOST, database="news_sources"
        )

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
        database = get_db()
        db.insert_mlb_tweet(database, tweet_id, author_handle, text, url, posted_at)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/tweets", methods=["GET"])
def get_tweets():
    """Query params: limit (default 100). Returns recent tweets from mlb_tweets (newest first)."""
    limit = min(500, max(1, int(request.args.get("limit", 100))))
    try:
        database = get_db()
        cursor = database.cursor(buffered=True)
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
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8765, debug=False)
