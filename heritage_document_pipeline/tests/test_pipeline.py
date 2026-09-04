import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pipeline


class PipelineTests(unittest.TestCase):
    def test_blocks_and_source_lines(self):
        text = (pipeline.ROOT / 'examples/synthetic_plan.md').read_text(encoding='utf-8')
        blocks = pipeline.split_articles(text)
        self.assertEqual(len(blocks), 5)
        for block in blocks:
            self.assertEqual('\n'.join(text.splitlines()[block['line_start']-1:block['line_end']]).strip(), block['text'])

    def test_blank_rejected(self):
        with self.assertRaises(ValueError):
            pipeline.split_articles(' \n ')

    def test_demo_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pipeline.ROOT / 'examples/synthetic_plan.md'
            out = Path(tmp) / 'run'
            manifest = pipeline.process(source, out, pipeline.FixtureBackend(source), city='示例城', period='2026-2036')
            self.assertEqual(manifest['entity_count'], 3)
            self.assertEqual(manifest['backend'], 'fixture-demo')
            self.assertIsNone(manifest['performance_claim'])
            entities = [json.loads(line) for line in (out / 'entities.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([e['name'] for e in entities], ['示例书院', '示例会馆', '示例南街'])

    def test_fixture_rejects_other_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'different.md'
            source.write_text('不同的输入', encoding='utf-8')
            with self.assertRaises(ValueError):
                pipeline.FixtureBackend(source)

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pipeline.ROOT / 'examples/synthetic_plan.md'
            out = Path(tmp)
            sentinel = out / 'keep.txt'
            sentinel.write_text('keep')
            with self.assertRaises(ValueError):
                pipeline.process(source, out, pipeline.FixtureBackend(source), city='', period='')
            self.assertEqual(sentinel.read_text(), 'keep')

    def test_ungrounded_entity_aborts(self):
        class BadBackend:
            name = 'test-only'
            def request(self, stage, block):
                if stage == 'index':
                    return {'category': 'background', 'summary': 'test'}
                return {'entities': [{'name': 'invented', 'category': 'test', 'evidence': 'invented'}]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'failed'
            with self.assertRaises(ValueError):
                pipeline.process(pipeline.ROOT / 'examples/synthetic_plan.md', out, BadBackend(), city='', period='')
            self.assertFalse(out.exists())

    def test_live_needs_explicit_consent(self):
        with self.assertRaises(ValueError):
            pipeline.LiveBackend(False)

    def test_schema_rejects_unknown_fields(self):
        with self.assertRaises(ValueError):
            pipeline.Entity.model_validate({'name': 'x', 'category': 'y', 'evidence': 'x', 'secret': 'no'})


if __name__ == '__main__':
    unittest.main()
