-- 故障知识：只收"模型疏忽"那层，且必须是抽象三元组 + 闭环验证过
CREATE TABLE IF NOT EXISTS fault (
  id            INTEGER PRIMARY KEY,
  symptom       TEXT NOT NULL,          -- 现象：什么操作，看到什么报错
  layer         TEXT NOT NULL,          -- syntax|type|api|dependency|env|tool|model|other
  pattern       TEXT NOT NULL,          -- 错误模式（抽象，不带具体变量名）
  fix           TEXT NOT NULL,          -- 修正模式（可复用）
  trigger_cond  TEXT,                   -- 触发条件：什么样的任务会遇上
  example       TEXT,                   -- 原始案例，只当证据，不参与注入
  evidence      TEXT,
  keywords      TEXT,                   -- 逗号分隔；召回时只能加分，不能压分
  verified      INTEGER NOT NULL DEFAULT 0,
  verified_how  TEXT,                   -- 怎么验证的（编译通过/返回 0/日志）
  verified_at   TEXT,
  hits          INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_fault_layer ON fault(layer, verified);
