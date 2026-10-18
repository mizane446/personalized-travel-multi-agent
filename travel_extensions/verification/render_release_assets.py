"""README graphics from measured receipts and real screenshots; Pillow is a docs-only dependency."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/travel/images'
FONT = Path('C:/Windows/Fonts/msyh.ttc')
BOLD = Path('C:/Windows/Fonts/msyhbd.ttc')


def font(size, bold=False):
    return ImageFont.truetype(str(BOLD if bold else FONT), size)


def label(draw, xy, text, size=22, color='#a8bbb5', bold=False):
    draw.text(xy, text, font=font(size, bold), fill=color)


def save(image, name):
    path = OUT / name
    if path.exists():
        raise FileExistsError('Use a new asset version; do not overwrite a published image')
    image.save(path)


def main():
    canvas = Image.new('RGB', (1600, 790), '#0a1918')
    d = ImageDraw.Draw(canvas)
    for x in range(1000, 1600, 75):
        d.line((x, 0, x - 240, 790), fill='#142e2b', width=1)
    d.rounded_rectangle((74, 62, 383, 102), radius=20, fill='#183b33')
    label(d, (92, 67), 'HERMES  /  TRAVEL EDITION', 17, '#a4e5c4', True)
    label(d, (70, 140), '让每一份旅行建议', 66, '#f3f7f4', True)
    label(d, (70, 233), '都有依据。', 82, '#c5e8b1', True)
    label(d, (76, 361), '原生子 Agent · 直接搜索 · 可溯源偏好 · 有来源的方案', 27, '#c1cec8')
    d.line((78, 431, 1520, 431), fill='#29433d', width=2)
    metrics = [('0.417 s', '搜索响应中位数', '18 次真实搜索 / 非整段对话耗时'),
               ('9 / 9', '模型调用观测完整', '一次受控链路 / 真实 Langfuse 入库'),
               ('MD + PDF', '可保存、可分享', '保留来源链接与待核实事项')]
    for i, (value, title, note) in enumerate(metrics):
        x = 80 + i * 500
        label(d, (x, 485), value, 48, '#f3f7f4', True)
        label(d, (x, 559), title, 26, '#c5e8b1')
        label(d, (x, 608), note, 18)
    label(d, (80, 728), 'BUILT ON HERMES  ·  INDEPENDENT EXTENSIONS  ·  EVIDENCE INCLUDED', 17, '#8eaaa1')
    save(canvas, 'release-hero-v1.png')

    canvas = Image.new('RGB', (1600, 840), '#eef3ee')
    d = ImageDraw.Draw(canvas)
    label(d, (50, 34), '从对话到有来源的旅行方案', 37, '#122c26', True)
    label(d, (52, 95), '左：官方 Desktop 合成验收  /  右：Sol 真实请求导出的 PDF', 20, '#486158')
    screen = Image.open(OUT / 'desktop-travel-v4.png').convert('RGB')
    screen = screen.crop((0, 0, screen.width, min(620, screen.height)))
    screen.thumbnail((1000, 440))
    d.rounded_rectangle((40, 150, 1070, 780), radius=20, fill='white', outline='#d0ded2', width=2)
    canvas.paste(screen, (55, 174))
    label(d, (75, 558), '保留官方桌面与执行链', 31, '#173e32', True)
    label(d, (75, 617), '偏好记录 → 子任务检索 → 来源审查 → 保存与导出', 22, '#486158')
    label(d, (75, 685), '增强模块独立维护，运行框架与桌面能力直接复用。', 21, '#486158')
    pdf = Image.open(OUT / 'plan-live-sol-v1.png').convert('RGB')
    pdf.thumbnail((440, 630))
    d.rounded_rectangle((1100, 150, 1560, 780), radius=18, fill='white', outline='#d0ded2', width=2)
    canvas.paste(pdf, (1110 + (440 - pdf.width) // 2, 160))
    save(canvas, 'release-showcase-v1.png')

    canvas = Image.new('RGB', (1600, 620), '#0a1918')
    d = ImageDraw.Draw(canvas)
    label(d, (60, 40), '复用运行框架，把改进放在业务边界', 37, '#f3f7f4', True)
    cards = [(60, '01  官方运行时', 'Desktop / Gateway', '模型循环 · 会话 · 原生子 Agent'),
             (555, '02  独立旅行增强', 'Search / Wiki / Review', '额度与权限 · 证据与冲突 · 来源校验'),
             (1050, '03  可交付结果', 'Plan / Export / Trace', '版本存储 · 中文 PDF · 调用用量')]
    for x, top, middle, bottom in cards:
        d.rounded_rectangle((x, 155, x + 450, 400), radius=18, fill='#142e28', outline='#345347', width=2)
        label(d, (x + 25, 184), top, 25, '#c5e8b1', True)
        label(d, (x + 25, 255), middle, 24, '#f3f7f4', True)
        label(d, (x + 25, 330), bottom, 20)
    for x in (520, 1015):
        label(d, (x, 248), '→', 28, '#c5e8b1')
    label(d, (65, 460), '核心源码保持基线。官方 Langfuse 使用独立、可回滚的固定版本兼容补丁。', 24, '#b5c9bf')
    label(d, (65, 523), '输入与来源可追溯；未知保持未知。运行正确不等于网页事实已经核实。', 21, '#8eaaa1')
    save(canvas, 'release-architecture-v1.png')


if __name__ == '__main__':
    main()
