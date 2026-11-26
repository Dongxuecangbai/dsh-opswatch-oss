-- 事实库（可选）：插件只读 regress，其余表和 ops.py 无关
CREATE TABLE IF NOT EXISTS subject (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, relation TEXT, note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS memory (
  id INTEGER PRIMARY KEY,
  subject_id INTEGER REFERENCES subject(id) ON DELETE SET NULL,
  kind TEXT NOT NULL DEFAULT 'fact',   -- fact|pref|event|quote|lesson
  body TEXT NOT NULL,
  weight INTEGER NOT NULL DEFAULT 3,
  source TEXT, tags TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated_at TEXT
);
-- 每条事实的出处
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY,
  memory_id INTEGER REFERENCES memory(id) ON DELETE CASCADE,
  source TEXT NOT NULL, quote TEXT,
  confidence INTEGER NOT NULL DEFAULT 3,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
-- 答错过的题：下次同类问题先查这里
CREATE TABLE IF NOT EXISTS regress (
  id INTEGER PRIMARY KEY,
  question TEXT NOT NULL, wrong TEXT, right TEXT,
  memory_id INTEGER REFERENCES memory(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'open',  -- open|fixed
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
