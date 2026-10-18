"""Render an evidence-led README case from real local screenshots (Pillow only)."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONT = 'C:/Windows/Fonts/msyh.ttc'
BOLD = 'C:/Windows/Fonts/msyhbd.ttc'


def text(draw, xy, value, size=24, fill='#46645a', bold=False):
    draw.text(xy, value, font=ImageFont.truetype(BOLD if bold else FONT, size), fill=fill)


def frame(source, crop, name, number, title, subtitle, note):
    shot = Image.open(source).convert('RGB').crop(crop)
    scale = min(1580 / shot.width, 1080 / shot.height)
    shot = shot.resize((round(shot.width * scale), round(shot.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (1680, shot.height + 250), '#edf3ef')
    draw = ImageDraw.Draw(canvas)
    text(draw, (50, 24), number + '  /  REAL RUN', 18, '#618276', True)
    text(draw, (50, 61), title, 38, '#123e30', True)
    text(draw, (50, 119), subtitle, 22)
    canvas.paste(shot, (50, 174))
    text(draw, (50, shot.height + 197), note, 18)
    path = ROOT / 'docs/travel/images' / name
    if path.exists():
        raise FileExistsError('Use a new version instead of replacing an artifact')
    canvas.save(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    canvas = Image.new('RGB', (1680, 720), '#0a1918')
    draw = ImageDraw.Draw(canvas)
    text(draw, (70, 55), 'HERMES  /  TRAVEL EDITION', 22, '#9bd2b6', True)
    text(draw, (70, 132), '让每一份旅行建议', 66, '#f4f8f5', True)
    text(draw, (70, 228), '都有依据。', 80, '#c5e8b1', True)
    text(draw, (75, 350), '原生子 Agent · 可溯源偏好 · 真实搜索 · 有来源的方案', 29, '#c1cec8')
    draw.line((75, 420, 1600, 420), fill='#29433d', width=2)
    for i, (value, label, note) in enumerate([
        ('3 个方向', '景点 / 餐饮 / 住宿', '同一次真实复杂任务'),
        ('18 / 18', '模型调用观测完整', '真实 Langfuse 入库，非成功率'),
        ('MD + PDF', '可保存、可追查', '保留来源链接与未核实事项'),
    ]):
        x = 80 + 525 * i
        text(draw, (x, 470), value, 48, '#f4f8f5', True)
        text(draw, (x, 545), label, 27, '#c5e8b1')
        text(draw, (x, 597), note, 21, '#9bb4aa')
    target = ROOT / 'docs/travel/images/release-hero-v2.png'
    if target.exists():
        raise FileExistsError('Use a new hero version')
    canvas.save(target)
    frame(args.run_dir / 'desktop-tools.png', (420, 450, 2158, 1380),
          'showcase-result-v2.png', '01', '杭州两日慢旅行：从复杂需求到可交付方案',
          '3 个研究方向 · 6 条审查结果 · 2 条偏好 · Markdown + PDF',
          '官方 Desktop 实际结果区域裁切。模型、搜索均为真实调用；需求人物为虚构。')
    frame(ROOT / '.hermes-runtime/lf-timeline.png', (184, 40, 1600, 1000),
          'showcase-langfuse-v2.png', '02', 'Langfuse：这一次任务的真实执行轨迹',
          '18/18 模型调用入库 · 10 次搜索 · 4 条关联 trace · 0 条错误观测',
          '图中为主 trace，子任务分别建 trace；顶部 token 仅为当前主 trace，非全链路总量。')
    frame(ROOT / '.hermes-runtime/lf-search-ready.png', (184, 40, 1500, 940),
          'showcase-search-v2.png', '03', '搜索不是一句结论：输入、结果和来源都可追查',
          '原生子 Agent → web_search → 豆包 HTTP → 官方来源 → 独立审查',
          '实际 Langfuse 搜索工具详情；候选引用还需与来源正文核对，不能把 HTTP 成功当事实正确。')


if __name__ == '__main__':
    main()
