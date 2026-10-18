"""Synthetic, public document fixture rendered by the production exporter."""
from pathlib import Path
import shutil
import tempfile

from travel_extensions.travel.plans import Plans
from travel_extensions.travel.research import Research
from travel_extensions.travel.wiki import WikiStore


def export_example(destination, version=1):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for suffix in ('md', 'pdf'):
        if (destination / (f'travel-example-v{version}.' + suffix)).exists():
            raise FileExistsError('Example already exists; choose a new output directory/version.')
    with tempfile.TemporaryDirectory() as tmp:
        state = Research(WikiStore(Path(tmp) / 'wiki'))
        state.begin('synthetic-demo', 'synthetic-requirement-v1')
        job = state.create('synthetic-demo', 'attraction', '杭州', '推荐两处适合散步的独立景点')
        state.finish(job, {'reviewed': True, 'complete': False, 'feedback': '当前只有一处候选，仍需补充第二处。',
            'accepted': [{'text': '合成示例：西湖散步。这里用于展示导出排版，不是实际检索结论；开放时间与天气待确认。',
                          'sources': ['https://example.org/synthetic-westlake']} ]})
        plans = Plans(state)
        plans.save('synthetic-demo', '杭州散步资料 - 合成展示样例', [job])
        outputs = plans.export('synthetic-demo')
        for format, path in outputs.items():
            target = destination / (f'travel-example-v{version}.' + ('md' if format == 'markdown' else 'pdf'))
            shutil.copyfile(path, target)
    return destination


if __name__ == '__main__':
    import sys
    print(export_example(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1))
