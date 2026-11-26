#!/usr/bin/env python3
"""干活用的库：工具、流程、卡点、故障模式。

事实与历史在 memory.db；这里只管怎么下手。
一条卡点要成立：现象 + 必做动作 + 证据；没证据的自动降级为未验证。
故障模式（fault）只收 model 层，且必须闭环验证过才算数。
"""
import argparse
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("OPS_DB") or os.path.join(HERE, "ops.db")
SQL = os.path.join(HERE, "ops.sql")
FAULT_SQL = os.path.join(HERE, "fault.sql")


def _find(name):
    """schema 可能在同级，也可能在 ../sql（仓库布局：cli/ 与 sql/ 是兄弟目录）。"""
    for p in (os.path.join(HERE, name), os.path.join(HERE, "..", "sql", name)):
        if os.path.exists(p):
            return p
    return None


def _script_files():
    return [p for p in (_find("ops.sql"), _find("fault.sql")) if p]


def migrate(c):
    """老库补列：新机器按 schema 建库，老机器靠这里补齐。"""
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "gate" not in tables:
        return
    cols = {r[1] for r in c.execute("PRAGMA table_info(gate)")}
    for name, ddl in [
        ("evidence", "ALTER TABLE gate ADD COLUMN evidence TEXT"),
        ("confidence", "ALTER TABLE gate ADD COLUMN confidence INTEGER NOT NULL DEFAULT 3"),
        ("verified", "ALTER TABLE gate ADD COLUMN verified INTEGER NOT NULL DEFAULT 0"),
        ("last_verified", "ALTER TABLE gate ADD COLUMN last_verified TEXT"),
    ]:
        if name not in cols:
            c.execute(ddl)
    if "fault" not in tables:
        return
    fcols = {r[1] for r in c.execute("PRAGMA table_info(fault)")}
    if "keywords" not in fcols:
        c.execute("ALTER TABLE fault ADD COLUMN keywords TEXT")


def conn(write=True):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    for path in _script_files():
        c.executescript(open(path, encoding="utf-8").read())
    migrate(c)
    if write:
        c.commit()
    return c


# ---------- 相似度 ----------

STOP = set("的了是在和把被就也都还又很个这那你我他她它吗呢吧啊着过要会能可以")


def bigrams(text):
    t = "".join(ch for ch in str(text or "").lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    if len(t) < 2:
        return set(t)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def content_chars(text):
    t = str(text or "").lower()
    return {ch for ch in t if (ch.isalnum() or "\u4e00" <= ch <= "\u9fff") and ch not in STOP}


def lexical(query, text):
    """字面重叠：去虚词后的一元重合率，与二元 Jaccard 取大。"""
    a, b = content_chars(query), content_chars(text)
    if not a or not b:
        return 0.0
    uni = len(a & b) / min(len(a), len(b))
    ba, bb = bigrams(query), bigrams(text)
    jac = len(ba & bb) / (len(ba) + len(bb) - len(ba & bb)) if (ba and bb) else 0.0
    return max(jac, uni * 0.9)


def score(row, query):
    """有 keywords 时：字面 0.5 + 关键词命中 0.5；没有就纯字面。"""
    text = " ".join(filter(None, [row["symptom"], row["pattern"], row["trigger_cond"], row["fix"]]))
    lex = lexical(query, text)
    kws = [k.strip() for k in str(row["keywords"] or "").replace("，", ",").split(",") if k.strip()]
    if not kws:
        return lex
    q = str(query).lower()
    hit = sum(1 for k in kws if k.lower() in q or lexical(q, k) >= 0.6) / len(kws)
    # 关键词只能加分，不能把字面命中多的条目压下去
    return max(lex, 0.5 * lex + 0.5 * hit)


def similarity(query, text):
    return lexical(query, text)


# ---------- 写 ----------

def cmd_tool_add(a):
    c = conn()
    with c:
        c.execute(
            "INSERT INTO tool(name, kind, how, notes, tags) VALUES(?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET kind=excluded.kind, how=excluded.how, "
            "notes=excluded.notes, tags=excluded.tags",
            (a.name, a.kind, a.how, a.notes, a.tags),
        )
    print(f"工具 {a.name} 记下了")


def cmd_tools(a):
    c = conn()
    for r in c.execute("SELECT * FROM tool ORDER BY name"):
        print(f"- {r['name']}: {r['how'][:90]}")
        if r["notes"]:
            print(f"    坑：{r['notes'][:80]}")


def cmd_gate_add(a):
    verified = 1 if a.verified else 0
    if verified and not a.evidence:
        print("--verified 必须配 -e（哪一次、怎么坏的）。已降级为未验证。")
        verified = 0
    c = conn()
    with c:
        cur = c.execute(
            "INSERT INTO gate(when_task, must_do, why, evidence, confidence, verified, last_verified) "
            "VALUES(?,?,?,?,?,?,CASE WHEN ?=1 THEN datetime('now','localtime') ELSE NULL END)",
            (a.when_task, a.must_do, a.why, a.evidence, a.confidence, verified, verified),
        )
    print(f"卡点 #{cur.lastrowid}（{'已验证' if verified else '未验证'}，置信 {a.confidence}）")


def cmd_verify(a):
    c = conn()
    table = "fault" if a.fault else "gate"
    if a.fault:
        with c:
            n = c.execute(
                "UPDATE fault SET verified=1, verified_how=COALESCE(?, verified_how), "
                "verified_at=datetime('now','localtime') WHERE id=?", (a.how, a.id)
            ).rowcount
    else:
        with c:
            n = c.execute(
                "UPDATE gate SET verified=1, last_verified=datetime('now','localtime') WHERE id=?", (a.id,)
            ).rowcount
    print(f"{table} #{a.id} 标成已验证。" if n else "没这个号。")


def cmd_play_add(a):
    c = conn()
    with c:
        c.execute(
            "INSERT INTO playbook(name, trigger, notes) VALUES(?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET trigger=excluded.trigger, notes=excluded.notes",
            (a.name, a.trigger, a.notes),
        )
        pid = c.execute("SELECT id FROM playbook WHERE name=?", (a.name,)).fetchone()[0]
    print(f"流程 {a.name} #{pid}（步骤没动）")


def cmd_step_add(a):
    c = conn()
    with c:
        cur = c.execute(
            "INSERT INTO step(playbook_id, ord, action, done_when) VALUES(?,?,?,?)",
            (a.play, a.ord, a.action, a.done),
        )
    print(f"步骤 #{cur.lastrowid} 挂上了")


def cmd_fault_add(a):
    verified = 1 if a.verified else 0
    if verified and not a.how:
        print("--verified 必须配 --how（怎么验证的）。已降级为未验证。")
        verified = 0
    if a.layer != "model":
        print(f"归因层是 {a.layer}，不是模型疏忽：照收，但不参与注入。")
    c = conn()
    with c:
        cur = c.execute(
            "INSERT INTO fault(symptom, layer, pattern, fix, trigger_cond, example, evidence, keywords, "
            "verified, verified_how, verified_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,CASE WHEN ?=1 THEN datetime('now','localtime') ELSE NULL END)",
            (a.symptom, a.layer, a.pattern, a.fix, a.trigger, a.example, a.evidence, a.keywords,
             verified, a.how, verified),
        )
    print(f"故障 #{cur.lastrowid}（{a.layer}，{'已验证' if verified else '未验证'}）")


def cmd_fault_list(a):
    c = conn()
    rows = c.execute(
        "SELECT * FROM fault WHERE (? IS NULL OR layer=?) ORDER BY verified DESC, id", (a.layer, a.layer)
    ).fetchall()
    for r in rows:
        print(f"#{r['id']} [{'✓' if r['verified'] else '?'}] {r['layer']}｜触发：{(r['trigger_cond'] or '')[:30]}")
        print(f"     错：{r['pattern'][:60]}")
        print(f"     改：{r['fix'][:60]}")


# ---------- 查 ----------

def cmd_before(a):
    c = conn()
    kw = a.keyword
    gates = c.execute(
        "SELECT * FROM gate WHERE when_task LIKE ? OR must_do LIKE ? ORDER BY verified DESC, id",
        (f"%{kw}%", f"%{kw}%"),
    ).fetchall()
    plays = c.execute(
        "SELECT * FROM playbook WHERE name LIKE ? OR trigger LIKE ?", (f"%{kw}%", f"%{kw}%")
    ).fetchall()
    if not gates and not plays:
        print(f"「{kw}」没有对应的卡点或流程记录。")
    for g in gates:
        mark = "已验证" if g["verified"] else "未验证，仅供参考"
        print(f"⚠ [{mark}] {g['when_task']}")
        print(f"   必做：{g['must_do']}")
        if g["why"]:
            print(f"   后果：{g['why']}")
        if g["evidence"]:
            print(f"   证据：{g['evidence']}")
    for p in plays:
        print(f"▶ {p['name']}")
        for s in c.execute("SELECT * FROM step WHERE playbook_id=? ORDER BY ord", (p["id"],)):
            print(f"   {s['ord']}. {s['action']}")
    n = c.execute("SELECT COUNT(*) n FROM fault WHERE layer='model'").fetchone()["n"]
    if n:
        print(f"（故障模式另有 {n} 条，用 recall 查，before 不负责这一层）")


def cmd_recall(a):
    """先按层/验证状态筛，再算分；不够像就不注入。"""
    c = conn()
    layer = None if a.all_layers else a.layer
    sql = "SELECT * FROM fault"
    conds, params = [], []
    if layer:
        conds.append("layer = ?")
        params.append(layer)
    if a.verified_only:
        conds.append("verified = 1")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    rows = c.execute(sql, params).fetchall()

    scored = []
    for r in rows:
        s = score(r, a.query)
        if s >= a.threshold:
            scored.append((s, r))
    scored.sort(key=lambda x: (-x[0], -x[1]["verified"]))

    if not scored:
        best = max((score(r, a.query) for r in rows), default=0.0)
        print(f"没有够像的（同层最高 {best:.2f}，阈值 {a.threshold}）。宁可不注入。")
        return

    for s, r in scored[: a.n]:
        with c:
            c.execute("UPDATE fault SET hits = hits + 1 WHERE id=?", (r["id"],))
        mark = "已验证" if r["verified"] else "未验证，只当线索"
        print(f"[{s:.2f}] #{r['id']} {mark}｜{r['layer']}")
        print(f"   错在哪：{r['pattern']}")
        print(f"   怎么改：{r['fix']}")
        if r["verified_how"]:
            print(f"   验证过：{r['verified_how']}")


def cmd_audit(a):
    c = conn()
    bad = c.execute(
        "SELECT id, when_task, confidence, verified FROM gate "
        "WHERE verified=0 OR confidence<3 OR evidence IS NULL ORDER BY id"
    ).fetchall()
    stale = c.execute(
        "SELECT id, when_task, last_verified FROM gate WHERE verified=1 AND "
        "(last_verified IS NULL OR julianday('now') - julianday(last_verified) > ?)", (a.days,)
    ).fetchall()
    fbare = c.execute("SELECT id, pattern FROM fault WHERE verified=0").fetchall()
    print(f"不可信 / 没证据的卡点：{len(bad)} 条")
    for r in bad:
        print(f"  #{r['id']} {r['when_task'][:34]}（置信 {r['confidence']}，{'已验证' if r['verified'] else '未验证'}）")
    if stale:
        print(f"超过 {a.days} 天没复核的：")
        for r in stale:
            print(f"  #{r['id']} {r['when_task'][:34]}（上次 {r['last_verified']}）")
    if fbare:
        print(f"没闭环的故障模式：{len(fbare)} 条 → " + ", ".join(f"#{r['id']}" for r in fbare))


def cmd_list(a):
    c = conn()
    print("卡点：")
    for g in c.execute("SELECT * FROM gate ORDER BY id"):
        print(f"  #{g['id']} [{'✓' if g['verified'] else '?'}] {g['when_task'][:30]} → {g['must_do'][:44]}")
    print("流程：")
    for p in c.execute("SELECT * FROM playbook ORDER BY id"):
        n = c.execute("SELECT COUNT(*) n FROM step WHERE playbook_id=?", (p["id"],)).fetchone()["n"]
        print(f"  #{p['id']} {p['name']}（{n} 步）")


LAYERS = ("syntax", "type", "api", "dependency", "env", "tool", "model", "other")

p = argparse.ArgumentParser(prog="ops")
sub = p.add_subparsers(dest="cmd", required=True)

s = sub.add_parser("tool")
s.add_argument("name")
s.add_argument("how")
s.add_argument("-k", "--kind")
s.add_argument("-n", "--notes")
s.add_argument("-t", "--tags")
s.set_defaults(func=cmd_tool_add)
s = sub.add_parser("tools")
s.set_defaults(func=cmd_tools)

s = sub.add_parser("gate")
s.add_argument("when_task")
s.add_argument("must_do")
s.add_argument("-w", "--why")
s.add_argument("-e", "--evidence")
s.add_argument("-c", "--confidence", type=int, default=3, choices=range(1, 6))
s.add_argument("--verified", action="store_true")
s.set_defaults(func=cmd_gate_add)

s = sub.add_parser("verify", help="置为已验证；--fault 时作用于故障模式")
s.add_argument("id", type=int)
s.add_argument("--fault", action="store_true")
s.add_argument("--how")
s.set_defaults(func=cmd_verify)

s = sub.add_parser("play")
s.add_argument("name")
s.add_argument("-t", "--trigger")
s.add_argument("-n", "--notes")
s.set_defaults(func=cmd_play_add)

s = sub.add_parser("step")
s.add_argument("play", type=int)
s.add_argument("ord", type=int)
s.add_argument("action")
s.add_argument("-d", "--done")
s.set_defaults(func=cmd_step_add)

s = sub.add_parser("fault")
s.add_argument("symptom")
s.add_argument("-l", "--layer", default="model", choices=LAYERS)
s.add_argument("-p", "--pattern", required=True)
s.add_argument("-f", "--fix", required=True)
s.add_argument("-t", "--trigger")
s.add_argument("-x", "--example")
s.add_argument("-e", "--evidence")
s.add_argument("-k", "--keywords", help="逗号分隔，召回时加权")
s.add_argument("--verified", action="store_true")
s.add_argument("--how")
s.set_defaults(func=cmd_fault_add)

s = sub.add_parser("faults")
s.add_argument("-l", "--layer")
s.set_defaults(func=cmd_fault_list)

s = sub.add_parser("recall", help="按相似度取，不够像就不给")
s.add_argument("query")
s.add_argument("-t", "--threshold", type=float, default=0.45)
s.add_argument("-n", type=int, default=3)
s.add_argument("-l", "--layer", default="model", help="默认只取模型疏忽那一层")
s.add_argument("--all-layers", action="store_true", help="连环境/依赖等层一起看")
s.add_argument("--verified-only", action="store_true")
s.set_defaults(func=cmd_recall)

s = sub.add_parser("before")
s.add_argument("keyword")
s.set_defaults(func=cmd_before)

s = sub.add_parser("audit")
s.add_argument("--days", type=int, default=30)
s.set_defaults(func=cmd_audit)

s = sub.add_parser("list")
s.set_defaults(func=cmd_list)

a = p.parse_args()
a.func(a)
