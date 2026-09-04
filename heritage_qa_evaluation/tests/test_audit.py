import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit


class AuditTests(unittest.TestCase):
    def test_missing_comma_only(self):
        fixed, offsets = audit.repair_adjacent_objects('{"messages":[{"role":"a"}{"role":"b"}]}')
        self.assertEqual(fixed, '{"messages":[{"role":"a"},{"role":"b"}]}')
        self.assertEqual(len(offsets), 1)

    def test_no_string_mutation(self):
        text = '{"x":"text }{ and escaped \\\" quote"}'
        self.assertEqual(audit.repair_adjacent_objects(text), (text, []))

    def test_duplicate_responses_rejected(self):
        with self.assertRaises(ValueError):
            audit.parse_responses('问题 1: a\n问题 1: b')

    def test_restarted_numbering_uses_question_text(self):
        records = audit.parse_responses('问题 1: first question\n问题 1: eleventh question', strict=False)
        questions = [{'question_id': 1, 'question': 'first question'}, {'question_id': 11, 'question': 'eleventh question'}]
        aligned = audit.align_responses(records, questions)
        self.assertEqual([r['question_id'] for r in aligned], [1, 11])
        self.assertEqual([r['original_question_id'] for r in aligned], [1, 1])

    def test_ambiguous_question_text_not_guessed(self):
        records = [{'question_id': 1, 'prompt_and_response': 'first question and second question'}]
        questions = [{'question_id': 1, 'question': 'first question'}, {'question_id': 2, 'question': 'second question'}]
        self.assertIsNone(audit.align_responses(records, questions)[0]['question_id'])

    def test_raw_scores_preserved(self):
        rows = [{'question_id': 1, 'condition': 'x', 'matched': 5, 'expected': 4}]
        before = copy.deepcopy(rows)
        correction = {'question_id': 1, 'condition': 'x', 'matched': 4, 'expected': 4,
                      'reviewer': 'test-only', 'reviewed_at': '2026-09-04', 'reason': 'fixture', 'evidence': 'fixture'}
        result = audit.apply_corrections(rows, [correction])
        self.assertEqual(rows, before)
        self.assertEqual(result[0]['matched'], 4)

    def test_unreviewed_correction_rejected(self):
        with self.assertRaises(ValueError):
            audit.apply_corrections([{'question_id': 1, 'condition': 'x'}],
                                    [{'question_id': 1, 'condition': 'x', 'matched': 4, 'expected': 4}])

    def test_invalid_question_excluded_for_every_model(self):
        rows = [{'question_id': q, 'condition': c, 'matched': 1, 'expected': 1}
                for c in audit.CONDITIONS for q in range(1, 21)]
        rows[13]['matched'] = 2
        evidence = {'raw_scores': rows, 'original_chart_values': [], 'responses': []}
        summary = audit.summarize(evidence, [])
        self.assertEqual(summary['excluded_question_ids_for_all_conditions'], [14])
        self.assertTrue(all(r['included_questions'] == 19 for r in summary['summaries']))
        self.assertFalse(summary['resume_percentage_approved'])

    def test_missing_scores_rejected(self):
        with self.assertRaises(ValueError):
            audit.summarize({'raw_scores': [], 'original_chart_values': [], 'responses': []}, [])

    def test_inconsistent_rubric_rejected(self):
        rows = [{'question_id': q, 'condition': c, 'matched': 1, 'expected': 1}
                for c in audit.CONDITIONS for q in range(1, 21)]
        rows[0]['expected'] = 2
        with self.assertRaises(ValueError):
            audit.summarize({'raw_scores': rows, 'original_chart_values': [], 'responses': []}, [])


if __name__ == '__main__':
    unittest.main()
