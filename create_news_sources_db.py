"""
Create the news_sources database and mlb_tweets table.
Uses DB connection from os_check (Windows: settings_win).
Run from project root: python create_news_sources_db.py
"""
import mysql.connector
from os_check import USER, PASSWORD, HOST

def main():
    # Connect without database to create the DB
    conn = mysql.connector.connect(user=USER, password=PASSWORD, host=HOST)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE DATABASE IF NOT EXISTS news_sources "
        "DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci"
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Connect to news_sources and create table
    conn = mysql.connector.connect(
        user=USER, password=PASSWORD, host=HOST, database="news_sources"
    )
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mlb_tweets (
          id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          tweet_id      VARCHAR(32)   NOT NULL COMMENT 'Twitter tweet ID',
          author_handle VARCHAR(255)  NOT NULL,
          text          TEXT          NOT NULL,
          url           VARCHAR(512)  DEFAULT NULL,
          posted_at     DATETIME      DEFAULT NULL COMMENT 'When the tweet was posted (from Twitter)',
          inserted_at   DATETIME      DEFAULT CURRENT_TIMESTAMP,
          UNIQUE KEY uq_tweet_id (tweet_id),
          KEY idx_posted_at (posted_at),
          KEY idx_author (author_handle)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("Database 'news_sources' and table 'mlb_tweets' are ready.")

if __name__ == "__main__":
    main()
