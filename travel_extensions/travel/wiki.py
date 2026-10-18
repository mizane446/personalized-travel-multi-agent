"""Independent evidence store following LLM Wiki's Raw/Wiki/Schema conventions.

No GPL application code is copied. SQLite is the authoritative journal; Markdown
is a repairable projection, not an extra editable source of truth.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import uuid
from contextlib import contextmanager

KEYS = ('food.diet', 'food.budget', 'hotel.budget', 'hotel.style',
        'attraction.style', 'general.mobility', 'general.other')


def identifier(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:24]


def atomic_text(path, text):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('不能写入符号链接')
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        temp.write_text(text, encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


class WikiStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.absolute() != self.root.resolve():
            raise ValueError('Wiki 目录不能包含链接')
        self.path = self.root / 'facts.db'
        if self.path.is_symlink():
            raise ValueError('数据库不能为链接')
        self._projection_lock = threading.RLock()
        for name in ('Raw', 'Wiki', 'Schema'):
            target = self.root / name
            if target.is_symlink():
                raise ValueError('Wiki 子目录不能为链接')
            target.mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS raw(id TEXT PRIMARY KEY, session TEXT, turn TEXT, text TEXT);
                CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY, key TEXT, quote TEXT,
                  source TEXT REFERENCES raw(id), status TEXT);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, fact TEXT, action TEXT);
            ''')
        self.project()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, session, turn, text):
        if not all(isinstance(x, str) and x for x in (session, turn, text)) or len(text) > 50000:
            raise ValueError('用户原话或会话标识无效')
        source = identifier(session, turn)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT text FROM raw WHERE id=?', (source,)).fetchone()
            if row and row['text'] != text:
                raise ValueError('相同消息不能改写原话')
            db.execute('INSERT OR IGNORE INTO raw VALUES (?,?,?,?)', (source, session, turn, text))
        self.project()
        return source

    def source_for(self, session, turn):
        with self.connect() as db:
            row = db.execute('SELECT id FROM raw WHERE session=? AND turn=?', (session, turn)).fetchone()
        return row['id'] if row else None

    def propose(self, source, key, quote):
        if key not in KEYS or not isinstance(quote, str) or not 1 <= len(quote.strip()) <= 500:
            raise ValueError('偏好字段或引用无效')
        quote = quote.strip()
        fact = identifier(source, key, quote)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            raw = db.execute('SELECT text FROM raw WHERE id=?', (source,)).fetchone()
            if not raw or quote not in raw['text']:
                raise ValueError('偏好必须逐字引用已有用户原话')
            if db.execute('SELECT id FROM facts WHERE id=?', (fact,)).fetchone():
                return fact
            previous = db.execute("SELECT quote FROM facts WHERE key=? AND status IN ('active','conflict')", (key,)).fetchall()
            conflict = any(row['quote'] != quote for row in previous)
            if conflict:
                db.execute("UPDATE facts SET status='conflict' WHERE key=? AND status='active'", (key,))
            db.execute('INSERT INTO facts VALUES (?,?,?,?,?)',
                       (fact, key, quote, source, 'conflict' if conflict else 'active'))
            db.execute('INSERT INTO events(fact,action) VALUES (?,?)', (fact, 'propose'))
        self.project()
        return fact

    def confirm(self, fact):
        """Only called from an exact user command, never from a model tool."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT key FROM facts WHERE id=? AND status!='forgotten'", (fact,)).fetchone()
            if not row:
                raise ValueError('偏好不存在')
            db.execute("UPDATE facts SET status='superseded' WHERE key=? AND status IN ('active','conflict')", (row['key'],))
            db.execute("UPDATE facts SET status='active' WHERE id=?", (fact,))
            db.execute("INSERT INTO events(fact,action) VALUES (?,'confirm')", (fact,))
        self.project()

    def forget(self, fact):
        """Soft removal from agent context; audit/raw retained and disclosed in docs."""
        with self.connect() as db:
            if not db.execute("UPDATE facts SET status='forgotten' WHERE id=?", (fact,)).rowcount:
                raise ValueError('偏好不存在')
            db.execute("INSERT INTO events(fact,action) VALUES (?,'forget')", (fact,))
        self.project()

    def facts(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM facts ORDER BY key,id')]

    def context(self):
        return json.dumps([f for f in self.facts() if f['status'] in {'active', 'conflict'}], ensure_ascii=False)

    def projections(self, db=None):
        if db is None:
            with self.connect() as snapshot:
                snapshot.execute('BEGIN')
                return self.projections(snapshot)
        else:
            raw = list(db.execute('SELECT * FROM raw ORDER BY id'))
            facts = [dict(row) for row in db.execute('SELECT * FROM facts ORDER BY key,id')]
            events = [dict(row) for row in db.execute('SELECT * FROM events ORDER BY id')]
        pages = {
            'purpose.md': '# 用途\n仅保存本 Hermes profile 的用户偏好。网页与模型回答不是用户原话。\n',
            'Schema/preferences.json': json.dumps({'version': 1, 'keys': KEYS, 'source': 'Raw/<id>.md',
                'rule': 'exact user quote; conflicting values require explicit confirmation'}, ensure_ascii=False, indent=2) + '\n',
            'Wiki/index.md': '# 索引\n\n[[preferences]]\n',
            'Wiki/log.md': '# 更新记录\n\n' + '\n'.join(json.dumps(e, ensure_ascii=False) for e in events) + '\n',
        }
        sources = sorted({f['source'] for f in facts})
        body = '---\nsources: ' + json.dumps(['../Raw/' + s + '.md' for s in sources]) + '\n---\n# 偏好事实\n\n'
        body += '\n'.join(f"- {f['key']} [{f['status']}] {json.dumps(f['quote'], ensure_ascii=False)} — [原话](../Raw/{f['source']}.md) · {f['id']}" for f in facts) + '\n'
        pages['Wiki/preferences.md'] = body
        for row in raw:
            pages[f"Raw/{row['id']}.md"] = f"---\nsource_id: {row['id']}\norigin: user\n---\n\n{row['text']}\n"
        return pages

    def project(self):
        with self._projection_lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for name, text in self.projections(db).items():
                path = self.root / name
                if not path.exists() or path.read_text('utf-8') != text:
                    atomic_text(path, text)

    def lint(self):
        problems = []
        for name, text in self.projections().items():
            path = self.root / name
            if not path.exists() or path.read_text('utf-8') != text:
                problems.append('projection mismatch: ' + name)
        return problems
