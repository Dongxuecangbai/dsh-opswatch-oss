PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS tool (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  kind TEXT,
  how TEXT NOT NULL,
  notes TEXT,
  tags TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS playbook (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  trigger TEXT,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS step (
  id INTEGER PRIMARY KEY,
  playbook_id INTEGER REFERENCES playbook(id) ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  action TEXT NOT NULL,
  done_when TEXT
);
-- 卡点：现象 + 必做动作 + 证据；没证据的默认未验证
CREATE TABLE IF NOT EXISTS gate (
  id INTEGER PRIMARY KEY,
  when_task TEXT NOT NULL,
  must_do TEXT NOT NULL,
  why TEXT,
  evidence TEXT,
  confidence INTEGER NOT NULL DEFAULT 3,
  verified INTEGER NOT NULL DEFAULT 0,
  last_verified TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
