"""Versioned documents built from reviewed evidence; export never calls an LLM.

Retains the old project's SQLite versioning and ReportLab approach without its
observer, subprocess fallback or independent person/session routing.
"""
from datetime import datetime, UTC
import json
from pathlib import Path
import tempfile
import uuid
from xml.sax.saxutils import escape

from .wiki import atomic_text, identifier


def render_pdf(title, markdown, target):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if not font.is_file():
        raise ValueError('中文 PDF 需要 Windows 微软雅黑字体 C:/Windows/Fonts/msyh.ttc')
    pdfmetrics.registerFont(TTFont('TravelChinese', str(font), subfontIndex=0))
    styles = {name: ParagraphStyle(name, fontName='TravelChinese', fontSize=size,
                                  leading=size * 1.6, spaceAfter=8, wordWrap='CJK')
              for name, size in [('title', 20), ('heading', 14), ('body', 10)]}
    story = [Paragraph(escape(title), styles['title']), Spacer(1, 8)]
    for line in markdown.splitlines():
        if not line.strip():
            story.append(Spacer(1, 5))
        else:
            heading = line.startswith('#')
            text = line.lstrip('#').strip() if heading else line
            story.append(Paragraph(escape(text), styles['heading' if heading else 'body']))
    def footer(canvas, doc):
        canvas.setFont('TravelChinese', 8)
        canvas.drawString(42, 24, '旅行资料整理 - 价格、营业与安全信息须再次确认')
        canvas.drawRightString(553, 24, str(doc.page))
    SimpleDocTemplate(str(target), pagesize=(595, 842), leftMargin=42, rightMargin=42,
                      topMargin=38, bottomMargin=42, title=title).build(story, onFirstPage=footer, onLaterPages=footer)


class Plans:
    def __init__(self, research):
        self.research = research
        self.wiki = research.wiki
        with self.wiki.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS plans(session TEXT,version INTEGER,title TEXT,
                          markdown TEXT,revision TEXT,PRIMARY KEY(session,version))''')

    def save(self, session, title, job_ids):
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError('方案标题为空或过长')
        if not isinstance(job_ids, list) or not 1 <= len(job_ids) <= 3 or any(not isinstance(j, str) for j in job_ids):
            raise ValueError('方案需要一至三个已审查任务')
        rows = [self.research.get(session, job) for job in dict.fromkeys(job_ids)]
        revision = rows[0]['revision']
        lines = []
        for row in rows:
            result = json.loads(row['result'] or '{}')
            if row['cancelled'] or not result.get('reviewed') or not result.get('accepted'):
                raise ValueError('取消、未审查或无合格候选的任务不能进入方案')
            lines += [f'## {row["destination"]} · {row["direction"]}', '', '要求：' + row['requirements'], '']
            for item in result['accepted']:
                lines += ['- ' + item['text'], '  来源：' + ' | '.join(item['sources']), '']
            if not result.get('complete'):
                lines += ['未完成项：' + result.get('feedback', '资料不完整'), '']
        lines += ['---', '价格、开放时间和过敏安全以出行前核实为准。', '需求版本：' + revision]
        markdown = '\n'.join(lines) + '\n'
        with self.wiki.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT revision FROM requirements WHERE session=?', (session,)).fetchone()
            if not current or current['revision'] != revision:
                raise ValueError('需求已变更，不能保存旧方案')
            for row in rows:
                live = db.execute('SELECT cancelled,result FROM jobs WHERE id=?', (row['id'],)).fetchone()
                if live['cancelled'] or live['result'] != row['result']:
                    raise ValueError('审查状态已变更，请重试')
            previous = db.execute('SELECT * FROM plans WHERE session=? ORDER BY version DESC LIMIT 1', (session,)).fetchone()
            if previous and previous['title'] == title and previous['markdown'] == markdown:
                return {'version': previous['version'], 'title': title}
            version = previous['version'] + 1 if previous else 1
            db.execute('INSERT INTO plans VALUES (?,?,?,?,?)', (session, version, title, markdown, revision))
        return {'version': version, 'title': title}

    def load(self, session, version=None):
        if version is not None and (type(version) is not int or version < 1):
            raise ValueError('版本必须是正整数')
        with self.wiki.connect() as db:
            row = db.execute('SELECT * FROM plans WHERE session=? AND version=?', (session, version)).fetchone() if version else db.execute(
                'SELECT * FROM plans WHERE session=? ORDER BY version DESC LIMIT 1', (session,)).fetchone()
        if row is None:
            raise ValueError('该会话没有此版本方案')
        return dict(row)

    def export(self, session, version=None, format='both'):
        if format not in ('markdown', 'pdf', 'both'):
            raise ValueError('导出格式必须为 markdown/pdf/both')
        plan = self.load(session, version)
        folder = self.wiki.root.parent / 'exports' / identifier(session)
        folder.mkdir(parents=True, exist_ok=True)
        if folder.absolute() != folder.resolve():
            raise ValueError('导出目录不能包含链接')
        name = f'plan-v{plan["version"]}-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}'
        paths = {}
        # Both outputs are prepared before publishing; failures leave no partial deliverable.
        with tempfile.TemporaryDirectory(dir=folder, prefix='.export-') as tmp:
            staged = Path(tmp)
            if format in ('markdown', 'both'):
                atomic_text(staged / 'plan.md', '# ' + plan['title'] + '\n\n' + plan['markdown'])
                paths['markdown'] = folder / (name + '.md')
            if format in ('pdf', 'both'):
                render_pdf(plan['title'], plan['markdown'], staged / 'plan.pdf')
                paths['pdf'] = folder / (name + '.pdf')
            for key, path in paths.items():
                (staged / ('plan.md' if key == 'markdown' else 'plan.pdf')).replace(path)
        return paths
