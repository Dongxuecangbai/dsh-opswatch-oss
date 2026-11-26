// 卡点：把干活踩过的坑摆到手机界面上。
// 数据：~/.opswatch/ops.db（gate 卡点、fault 故障模式）、~/.opswatch/memory.db（regress 错题）。
// 两张库各自 try/catch，一张表挂了不许拖垮状态条。
import { DatabaseSync } from 'node:sqlite'
import { homedir } from 'node:os'

export const name = 'local-opswatch'

const HOME = process.env.HOME || homedir() || '.'
const OPS_DB = process.env.OPSWATCH_DB || HOME + '/.opswatch/ops.db'
const MEM_DB = process.env.OPSWATCH_MEM || HOME + '/.opswatch/memory.db'
const OPS = process.env.OPSWATCH_CLI || HOME + '/.opswatch/ops.py'

function one(dbPath, sql, fallback = null) {
  try {
    const db = new DatabaseSync(dbPath, { readOnly: true })
    const row = db.prepare(sql).get()
    db.close()
    return row ? Number(row[Object.keys(row)[0]]) : fallback
  } catch {
    return fallback
  }
}

function tally() {
  return {
    g: one(OPS_DB, 'SELECT COUNT(*) AS n FROM gate'),
    f: one(OPS_DB, 'SELECT COUNT(*) AS n FROM fault'),
    r: one(MEM_DB, "SELECT COUNT(*) AS n FROM regress WHERE status = 'open'"),
  }
}

export function apply(ctx) {
  ctx.inject(['dshGo'], (ctx) => {
    ctx.dshGo.strip('counts', (scope, emit, caps) => {
      const zh = !String(caps.locale).startsWith('en')
      const tick = () => {
        const { g, f, r } = tally()
        const parts = []
        if (g !== null) parts.push((zh ? '卡点 ' : 'G ') + g)
        if (f !== null) parts.push((zh ? '故障 ' : 'F ') + f)
        if (r !== null) parts.push((zh ? '错题 ' : 'R ') + r)
        if (parts.length === 0) {
          return emit({ text: zh ? '库读不到' : 'DB unreadable', icon: 'warning', tone: 'warn' })
        }
        const text = parts.join(' · ')
        emit({ text: text.length > 24 ? text.slice(0, 24) : text, icon: 'warning', tone: r === null || r === 0 ? 'info' : 'warn' })
      }
      tick()
      const timer = setInterval(tick, 60_000)
      return () => clearInterval(timer)
    })

    // 有字 → 召回故障；空着 → 生成开工前查卡点的命令
    ctx.dshGo.on('check', (scope, event) => {
      const zh = !String(event.locale).startsWith('en')
      const q = String(scope.draft ?? '').trim()
      if (q === '') {
        return { insert: 'python3 ' + OPS + ' before ', toast: zh ? '补上任务名再发' : 'Add a task keyword' }
      }
      return { insert: 'python3 ' + OPS + ' recall "' + q.slice(0, 40) + '"', toast: zh ? '召回命令已放好' : 'Recall inserted' }
    })

    // 输入框内容记成一条卡点（未验证）：第一行"什么时候"，其余"必做"
    ctx.dshGo.on('log', (scope, event) => {
      const zh = !String(event.locale).startsWith('en')
      const text = String(scope.draft ?? '').trim()
      if (text === '') return { toast: zh ? '输入框是空的' : 'The composer is empty' }
      const lines = text.split('\n').filter((l) => l.trim() !== '')
      const when = lines[0].replace(/^[-*\d.、\s]+/, '').slice(0, 80)
      const must = (lines.slice(1).join(' ') || when).slice(0, 300)
      try {
        const db = new DatabaseSync(OPS_DB)
        db.prepare(
          'INSERT INTO gate(when_task, must_do, why, evidence, confidence, verified) VALUES(?,?,?,?,?,0)',
        ).run(when, must, null, zh ? '插件手动记入' : 'logged from plugin', 2)
        db.close()
        return { toast: zh ? '记下了（未验证）：' + when.slice(0, 10) : 'Saved (unverified)' }
      } catch {
        return { toast: zh ? '没写进去，库打不开' : 'Could not write' }
      }
    })

    ctx.dshGo.panel('gates', {
      view: () => ({
        v: 2,
        type: 'stack',
        title: '卡点与故障',
        children: [
          {
            type: 'keyValue',
            items: [
              ['卡点', { $: 'data.g' }],
              ['故障模式', { $: 'data.f' }],
              ['未修错题', { $: 'data.r' }],
            ],
          },
          { type: 'text', text: { $: 'data.hint' }, tone: 'muted' },
          { type: 'text', text: { $: 'data.sec1' } },
          { type: 'list', items: { $: 'data.gates' } },
          { type: 'text', text: { $: 'data.sec2' } },
          { type: 'list', items: { $: 'data.faults' } },
          { type: 'text', text: { $: 'data.sec3' } },
          { type: 'list', items: { $: 'data.regress' } },
          { type: 'actions', items: [{ label: '生成开工命令', action: 'cmd' }] },
        ],
      }),
      data: (scope, emit, caps) => {
        const zh = !String(caps.locale).startsWith('en')
        const pull = () => {
          const out = {
            g: '—', f: '—', r: '—',
            hint: zh ? '✓ 已验证，? 只是线索。开工前先看一遍。' : '✓ verified, ? lead only.',
            sec1: zh ? '卡点' : 'Gates', sec2: zh ? '故障模式（只注入 model 层）' : 'Faults (model only)',
            sec3: zh ? '答错的旧题' : 'Regressions',
            gates: [], faults: [], regress: [],
          }
          try {
            const db = new DatabaseSync(OPS_DB, { readOnly: true })
            const gates = db.prepare('SELECT id, when_task, must_do, verified FROM gate ORDER BY verified DESC, id').all()
            const faults = db.prepare('SELECT id, layer, pattern, fix, verified FROM fault ORDER BY verified DESC, id').all()
            db.close()
            out.g = gates.length
            out.f = faults.length
            out.gates = gates.map((x) => ({
              title: (x.verified ? '✓ ' : '? ') + String(x.when_task).slice(0, 36),
              subtitle: String(x.must_do).slice(0, 60),
              tone: x.verified ? undefined : 'warn',
            }))
            out.faults = faults.map((x) => ({
              title: (x.verified ? '✓ ' : '? ') + x.layer + '｜' + String(x.pattern).slice(0, 30),
              subtitle: String(x.fix).slice(0, 52),
              tone: x.layer === 'model' ? (x.verified ? 'good' : 'warn') : undefined,
            }))
          } catch {
            out.hint = zh ? 'ops 库读不到：' + OPS_DB : 'ops db unreadable'
          }
          try {
            const mem = new DatabaseSync(MEM_DB, { readOnly: true })
            const reg = mem.prepare("SELECT id, question, wrong FROM regress WHERE status = 'open' ORDER BY id").all()
            mem.close()
            out.r = reg.length
            out.regress = reg.map((x) => ({
              title: '错题 ' + x.id + '：' + String(x.question).slice(0, 28),
              subtitle: '答过：' + String(x.wrong ?? '').slice(0, 24),
              tone: 'warn',
              action: { id: 'fix', args: { id: Number(x.id) } },
            }))
          } catch {
            out.r = '—'
          }
          emit(out)
        }
        pull()
        const timer = setInterval(pull, 30_000)
        return () => clearInterval(timer)
      },
      actions: {
        cmd: () => ({ insert: 'python3 ' + OPS + ' before ', toast: '补上任务名再发' }),
        fix: (scope, event) => {
          const id = Number(event.value?.id)
          if (!Number.isFinite(id)) return { toast: '没拿到编号' }
          try {
            const mem = new DatabaseSync(MEM_DB)
            mem.prepare("UPDATE regress SET status = 'fixed' WHERE id = ?").run(id)
            mem.close()
            return { toast: '错题 ' + id + ' 标成修好了', refresh: true }
          } catch {
            return { toast: '改不动，库打不开' }
          }
        },
      },
    })
  })
}
