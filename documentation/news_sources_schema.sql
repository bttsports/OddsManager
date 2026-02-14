-- Database: news_sources
-- Table: mlb_tweets — all tweets (text and data); player/team organization later.

CREATE DATABASE IF NOT EXISTS news_sources
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE news_sources;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
