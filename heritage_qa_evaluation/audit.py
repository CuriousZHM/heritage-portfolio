"""Reconstruct and audit archived coursework evidence. No model/network calls.

Import source files once, then render all results from evidence/evaluation.json.
Corrections are separate, reviewer-attributed records, never in-place raw-score edits.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import statistics
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart'}
CONDITIONS = ['feed-dsr1-32b', 'feed-gemma3-27b', 'feed-llama3.3-70b',
              'llm-dsr1-32b', 'llm-gemma3-27b', 'llm-llama3.3-70b',
              'rag-hybrid-dsr1-32b', 'rag-hybrid-gemma3-27b', 'rag-hybrid-llama3.3-70b']


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fingerprint(path: Path) -> dict:
    return {'filename': path.name, 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def repair_adjacent_objects(line: str) -> tuple[str, list[int]]:
    """Only insert a missing comma between adjacent JSON objects outside strings."""
    out, fixes = [], []
    in_string = escaped = False
    last_significant = ''
    stack = []
    for pos, char in enumerate(line):
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
                last_significant = '"'
            continue
        if char == '"':
            in_string = True
        elif char == '{':
            if last_significant == '}' and stack and stack[-1] == '[':
                out.append(',')
                fixes.append(pos)
            stack.append('{')
        elif char == '[':
            stack.append('[')
        elif char in '}]':
            if stack:
                stack.pop()
        out.append(char)
        if not char.isspace():
            last_significant = char
    return ''.join(out), fixes


def import_questions(path: Path) -> tuple[list[dict], list[dict]]:
    questions, repairs = [], []
    for line_number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            repaired, positions = repair_adjacent_objects(line)
            record = json.loads(repaired)  # anything else malformed fails; never guess text
            repairs.append({'source_line': line_number, 'operation': 'insert missing JSON comma',
                            'character_offsets': positions, 'content_changed': False})
        messages = record['messages']
        def one(role: str) -> str:
            found = [m['content'] for m in messages if m['role'] == role]
            if len(found) != 1:
                raise ValueError(f'Expected one {role} message on source line {line_number}')
            return found[0]
        questions.append({'question_id': len(questions) + 1, 'question': one('user'),
                          'reference_context': one('information_retriever'),
                          'reference_answer': one('assistant'), 'source_line': line_number,
                          'reference_points': None, 'rubric_status': 'point-level rubric not recovered'})
    if len(questions) != 20:
        raise ValueError(f'Expected 20 archived questions; found {len(questions)}')
    return questions, repairs


def import_scores(path: Path) -> tuple[list[dict], list[dict]]:
    scores, chart_values = [], []
    with zipfile.ZipFile(path) as deck:
        for slide in [7, 8]:
            root = ET.fromstring(deck.read(f'ppt/slides/slide{slide}.xml'))
            for table in root.findall('.//a:tbl', NS):
                for tr in table.findall('a:tr', NS):
                    cells = [''.join(t.text or '' for t in tc.findall('.//a:t', NS)) for tc in tr.findall('a:tc', NS)]
                    if not cells or not re.fullmatch(r'Question\s+\d+', cells[0]):
                        continue
                    if len(cells) != 10:
                        raise ValueError('Unexpected PPT score-table width')
                    qid = int(cells[0].split()[-1])
                    for condition, value in zip(CONDITIONS, cells[1:]):
                        match = re.fullmatch(r'(\d+)\s*/\s*(\d+)', value.strip())
                        if not match:
                            raise ValueError(f'Invalid score notation for question {qid}')
                        scores.append({'question_id': qid, 'condition': condition,
                                       'matched': int(match[1]), 'expected': int(match[2]),
                                       'original_text': value, 'source': f'{path.name}, slide {slide}'})
        chart = ET.fromstring(deck.read('ppt/charts/chart1.xml'))
        for series in chart.findall('.//c:ser', NS):
            name = series.find('.//c:tx//c:v', NS).text
            categories = [p.find('c:v', NS).text for p in series.findall('.//c:cat//c:pt', NS)]
            values = [float(p.find('c:v', NS).text) for p in series.findall('.//c:val//c:pt', NS)]
            for category, value in zip(categories, values):
                prefix = {'hand-pick': 'feed', 'llm': 'llm', 'rag': 'rag-hybrid'}[category]
                chart_values.append({'condition': f'{prefix}-{name}', 'value': value,
                                     'source': f'{path.name}, slide 9, chart1'})
    if len(scores) != 180:
        raise ValueError(f'Expected 180 archived scores; found {len(scores)}')
    return scores, chart_values


def parse_responses(text: str, strict: bool = True) -> list[dict]:
    pieces = re.split(r'(?m)^问题\s*(\d+)\s*[：:]\s*', text)
    records = []
    for index in range(1, len(pieces), 2):
        records.append({'question_id': int(pieces[index]), 'prompt_and_response': pieces[index + 1].strip()})
    ids = [r['question_id'] for r in records]
    if strict and len(ids) != len(set(ids)):
        raise ValueError('Duplicate question identifiers in response file')
    occurrences = {}
    for record in records:
        qid = record['question_id']
        occurrences[qid] = occurrences.get(qid, 0) + 1
        record['occurrence'] = occurrences[qid]
    return records


def align_responses(records: list[dict], questions: list[dict]) -> list[dict]:
    """Use a unique exact question-text match; never infer identity from row order."""
    aligned = []
    for record in records:
        text = record['prompt_and_response']
        matches = [q['question_id'] for q in questions if q['question'].strip() in text]
        aligned.append({**record, 'original_question_id': record['question_id'],
                        'question_id': matches[0] if len(matches) == 1 else None,
                        'alignment': 'unique exact question text' if len(matches) == 1 else 'unresolved',
                        'candidate_question_ids': matches})
    return aligned


def import_evidence(source_dir: Path, evidence_path: Path) -> dict:
    qa_path = source_dir / 'data/8021manually_picked_QA.jsonl'
    deck_path = source_dir / '8021project-eval.pptx'
    questions, repairs = import_questions(qa_path)
    scores, charts = import_scores(deck_path)
    sources = [fingerprint(qa_path), fingerprint(deck_path)]
    responses = []
    for path in sorted((source_dir / 'output/output').glob('output-*.txt')):
        raw_text = path.read_text(encoding='utf-8-sig')
        records = align_responses(parse_responses(raw_text, strict=False), questions)
        ids = [r['question_id'] for r in records]
        duplicates = sorted({qid for qid in ids if qid is not None and ids.count(qid) > 1})
        responses.append({'file': path.name, 'records': records, 'raw_text': raw_text,
                          'duplicate_question_ids': duplicates,
                          'score_alignment': 'unresolved' if duplicates or None in ids or not ids else
                          'exact question text matched; no point-level regrading'})
        sources.append(fingerprint(path))
    evidence = {'schema_version': 1, 'experiment': 'STAT8021 coursework, 2025',
                'maintenance_date': '2026-09-04', 'sources': sources, 'questions': questions,
                'raw_scores': scores, 'original_chart_values': charts,
                'responses': responses, 'format_repairs': repairs,
                'attribution': {'Haiming Zhu': ['overall concept', 'dataset curation', 'evaluation design', 'evaluation report'],
                                'teammates': ['implementation', 'experiment execution'],
                                'maintenance': 'AI-assisted evidence packaging and arithmetic audit, September 2026'},
                'warning': 'Historical legal-information experiment. Not current legal advice. No model rerun or new human scoring.'}
    save_json(evidence_path, evidence)
    return evidence


def apply_corrections(raw_scores: list[dict], corrections: list[dict]) -> list[dict]:
    rows = [dict(r) for r in raw_scores]
    lookup = {(r['question_id'], r['condition']): r for r in rows}
    if len(lookup) != len(rows):
        raise ValueError('Duplicate score identifiers')
    seen = set()
    for correction in corrections:
        key = (correction['question_id'], correction['condition'])
        if key in seen or key not in lookup:
            raise ValueError('Duplicate or unknown correction identifier')
        seen.add(key)
        for field in ['reviewer', 'reviewed_at', 'reason', 'evidence']:
            if not correction.get(field):
                raise ValueError(f'Correction requires {field}')
        for field in ['matched', 'expected']:
            if type(correction.get(field)) is not int:
                raise ValueError('Corrected counts must be integers')
        if not 0 <= correction['matched'] <= correction['expected'] or correction['expected'] <= 0:
            raise ValueError('Corrected counts out of range')
        lookup[key].update({k: correction[k] for k in ['matched', 'expected']})
        lookup[key]['correction'] = correction
    return rows


def summarize(evidence: dict, corrections: list[dict]) -> dict:
    rows = apply_corrections(evidence['raw_scores'], corrections)
    invalid = [r for r in rows if not (type(r['matched']) is int and type(r['expected']) is int
               and r['expected'] > 0 and 0 <= r['matched'] <= r['expected'])]
    excluded = {r['question_id'] for r in invalid}
    for qid in range(1, 21):
        denominators = {r['expected'] for r in rows if r['question_id'] == qid}
        if len(denominators) > 1:
            raise ValueError(f'Question {qid} has inconsistent reference-point counts; review all conditions together')
    # A shared question set avoids comparing models on different subsets.
    summaries = []
    for condition in CONDITIONS:
        all_rows = [r for r in rows if r['condition'] == condition]
        if len(all_rows) != 20 or {r['question_id'] for r in all_rows} != set(range(1, 21)):
            raise ValueError('Missing question scores')
        eligible = [r for r in all_rows if r['question_id'] not in excluded]
        summaries.append({'condition': condition, 'included_questions': len(eligible),
                          'matched': sum(r['matched'] for r in eligible),
                          'expected': sum(r['expected'] for r in eligible),
                          'macro_coverage': statistics.mean(r['matched']/r['expected'] for r in eligible) if eligible else None,
                          'micro_coverage': sum(r['matched'] for r in eligible)/sum(r['expected'] for r in eligible) if eligible else None,
                          'status': 'arithmetic only; reference rubric not revalidated'})
    chart_checks = []
    for chart in evidence['original_chart_values']:
        matching = [r for r in rows if r['condition'] == chart['condition']]
        if not matching:
            raise ValueError('Chart condition not found in score table')
        macro = statistics.mean(r['matched']/r['expected'] for r in matching)
        micro = sum(r['matched'] for r in matching)/sum(r['expected'] for r in matching)
        chart_checks.append({**chart, 'raw_table_macro': macro, 'raw_table_micro': micro,
                             'matches_either_at_two_decimals': chart['value'] in {round(macro, 2), round(micro, 2)},
                             'contains_invalid_score': any(r['question_id'] in excluded for r in matching),
                             'purpose': 'reconciliation only, not a valid experimental result'})
    missing_responses = [{'file': f['file'], 'missing_question_ids': sorted(set(range(1, 21)) - {r['question_id'] for r in f['records']}),
                          'duplicate_question_ids': f.get('duplicate_question_ids', [])}
                         for f in evidence['responses'] if {r['question_id'] for r in f['records']} != set(range(1, 21)) or f.get('duplicate_question_ids')]
    return {'metric': 'reference-answer point coverage (recall-like), not precision or accuracy',
            'aggregation': 'macro = mean per-question coverage; micro = total matched / total reference points',
            'excluded_question_ids_for_all_conditions': sorted(excluded), 'invalid_scores': invalid,
            'summaries': summaries, 'original_chart_reconciliation': chart_checks,
            'response_files': len(evidence['responses']), 'incomplete_response_files': missing_responses,
            'resume_percentage_approved': False,
            'unresolved': ['Point-level reference rubric and match annotations have not been recovered.',
                           'Question 1 score denominator is 17, but the illustrative slide uses 8 points; reconcile granularity.',
                           'Question 14 contains 5/4 in two legacy cells; do not silently cap or change the denominator.',
                           'No blind or independent regrading, held-out-set confirmation, timing baseline, or confidence interval.']}


def render(evidence: dict, summary: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(output_dir / 'summary.json', summary)
    save_json(output_dir / 'review_queue.json', {'invalid_scores': summary['invalid_scores'], 'questions': summary['unresolved']})
    def esc(value) -> str:
        return html.escape(str(value))
    table_rows = []
    for row in summary['summaries']:
        macro, micro = row['macro_coverage'], row['micro_coverage']
        table_rows.append('<tr>' + ''.join(f'<td>{esc(x)}</td>' for x in [row['condition'], row['included_questions'],
                          f'{row["matched"]}/{row["expected"]}', f'{macro:.2%}' if macro is not None else 'N/A',
                          f'{micro:.2%}' if micro is not None else 'N/A']) + '</tr>')
    invalid_rows = ''.join('<li>' + esc(f'Question {r["question_id"]}, {r["condition"]}: {r["original_text"]}') + '</li>'
                           for r in summary['invalid_scores'])
    chart_checks = ''.join('<tr>' + ''.join(f'<td>{esc(x)}</td>' for x in [r['condition'], f'{r["value"]:.2%}',
                          f'{r["raw_table_macro"]:.2%}', f'{r["raw_table_micro"]:.2%}', r['matches_either_at_two_decimals']]) + '</tr>'
                          for r in summary['original_chart_reconciliation'])
    question_details = []
    for q in evidence['questions']:
        answer_details = []
        for response_file in evidence['responses']:
            for record in response_file['records']:
                if record['question_id'] != q['question_id']:
                    continue
                body = record['prompt_and_response']
                answer_marker = re.search(r'(?m)^回答(?:\s*\d+)?\s*[：:]\s*', body)
                if answer_marker:
                    body = body[answer_marker.end():]
                body = re.sub(r'<think>.*?</think>', '[Archived reasoning omitted from this display]', body, flags=re.S)
                answer_details.append(f'<details><summary>{esc(response_file["file"])} '
                    f'(original Q{record["original_question_id"]})</summary><pre>{esc(body)}</pre></details>')
        question_details.append(f'<details><summary>Q{q["question_id"]}: {esc(q["question"])}</summary>'
            f'<h3>Archived reference answer</h3><pre>{esc(q["reference_answer"])}</pre>'
            f'<h3>Archived reference context</h3><pre>{esc(q["reference_context"])}</pre>'
            f'<h3>Responses aligned by exact question text</h3>{"".join(answer_details)}</details>')
    details = ''.join(question_details)
    chart_parts = ['<svg viewBox="0 0 1040 400" role="img" aria-label="Recomputed legacy macro coverage, not validated model accuracy">']
    for tick in [0, 0.5, 1]:
        x = 320 + 620 * tick
        chart_parts.append(f'<line x1="{x}" y1="25" x2="{x}" y2="370" stroke="#ddd"/>'
                           f'<text x="{x}" y="18" text-anchor="middle" font-size="13">{tick:.0%}</text>')
    for i, row in enumerate(summary['summaries']):
        y = 42 + i * 37
        value = row['macro_coverage']
        color = '#50677e' if row['condition'].startswith('feed-') else ('#aa744b' if row['condition'].startswith('llm-') else '#347b73')
        chart_parts.append(f'<text x="305" y="{y+16}" text-anchor="end" font-size="14">{esc(row["condition"])}</text>')
        if value is not None:
            chart_parts.append(f'<rect x="320" y="{y}" width="{620*value:.2f}" height="23" fill="{color}"/>'
                               f'<text x="{330+620*value:.2f}" y="{y+16}" font-size="13">{value:.1%}</text>')
    chart_parts.append('</svg>')
    coverage_chart = ''.join(chart_parts)
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Heritage Q&A evaluation audit</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:1150px;margin:36px auto;padding:0 24px;color:#222}}
h1{{font-size:28px}}h2{{margin-top:32px}}table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{padding:8px 12px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#f3f5f7}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}}details{{padding:12px 0;border-bottom:1px solid #ddd}}
.notice{{border-left:4px solid #a66e00;padding:12px 18px;background:#fff7e8}}</style>
<h1>Heritage Q&A evaluation audit</h1><p>STAT8021 coursework (2025). Evidence reconstruction: September 2026.</p>
<p class="notice">This is an arithmetic audit of archived manual scores, not a new experiment or a certified accuracy result.
No model was rerun. No missing score was guessed. Do not use these percentages in a CV.</p>
<h2>Personal contribution</h2><p>Haiming Zhu: overall concept, dataset curation, evaluation design and report preparation.
Teammates: implementation and experiment execution. This packaging is later AI-assisted maintenance.</p>
<h2>Metric definition</h2><p>{esc(summary['metric'])}. {esc(summary['aggregation'])}.
Coverage alone does not penalize unsupported additional claims. Literal answer accuracy, retrieval quality and latency are separate measures.</p>
<h2>Unresolved original scores</h2><ul>{invalid_rows}</ul><p>Questions excluded from <em>all</em> conditions for the comparison below:
{esc(summary['excluded_question_ids_for_all_conditions'])}. Remaining numbers retain historical annotations and still require rubric validation.</p>
<h2>Recomputed legacy coverage on the common valid subset</h2>
<table><thead><tr><th>Condition</th><th>Questions</th><th>Matched/reference</th><th>Macro</th><th>Micro</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table>
<h2>Legacy coverage chart</h2><p>Same macro values and shared question subset as the table above.
Arithmetic audit only, not regraded model accuracy. Feed = manually supplied context; LLM = no extra context.</p>{coverage_chart}
<h2>Original chart reconciliation</h2><p>This diagnostic table uses all original cells, including invalid ones, to trace the old chart.
It must not be interpreted as valid performance.</p><table><tr><th>Condition</th><th>Old chart</th><th>Raw macro</th><th>Raw micro</th><th>Rounded match</th></tr>{chart_checks}</table>
<h2>Evidence inventory</h2><p>{len(evidence['questions'])} questions, {len(evidence['raw_scores'])} original score cells,
{len(evidence['responses'])} response files. {len(evidence['format_repairs'])} JSON lines needed syntax-only repair.</p>
<p>Files whose records could not all be aligned automatically: {esc(summary['incomplete_response_files'])}.
Unparsed text is preserved in the evidence JSON; an absent parsed record does not prove an absent experiment.</p>
<h2>Review requirements</h2><ul>{''.join('<li>'+esc(x)+'</li>' for x in summary['unresolved'])}</ul>
<h2>Archived questions and reference answers</h2><p>Historical source text only, not current legal guidance.</p>{details}
<h2>Provenance</h2><p>All tables above derive from evidence/evaluation.json through audit.py.
Original files remain unchanged. Source hashes and syntax repair records are retained in that JSON.
Raw scores are immutable inputs; reviewer-attributed corrections go in corrections.json.</p></html>'''
    (output_dir / 'evaluation_report.html').write_text(document, encoding='utf-8')
    lines = ['# Evaluation findings', '', 'No CV-ready performance percentage is approved.', '',
             '- Source: archived STAT8021 coursework, not a new experiment.',
             '- Metric corrected to reference-answer point coverage (recall-like).',
             '- Raw scores preserved. Invalid cells excluded through a shared question set, never capped.',
             '- All generated summaries share one evidence JSON and one calculation function.',
             f'- Questions: {len(evidence["questions"])}; score cells: {len(evidence["raw_scores"])}; response files: {len(evidence["responses"])}.',
             '', '## Outstanding reviewer decisions', *['- ' + x for x in summary['unresolved']]]
    (output_dir / 'FINDINGS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, help='Import originals; never modifies them')
    parser.add_argument('--evidence', type=Path, default=ROOT / 'evidence/evaluation.json')
    parser.add_argument('--corrections', type=Path, default=ROOT / 'corrections.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports')
    args = parser.parse_args()
    evidence = import_evidence(args.source_dir, args.evidence) if args.source_dir else json.loads(args.evidence.read_text(encoding='utf-8'))
    corrections = json.loads(args.corrections.read_text(encoding='utf-8'))
    summary = summarize(evidence, corrections)
    render(evidence, summary, args.output)
    print(json.dumps({'questions': len(evidence['questions']), 'scores': len(evidence['raw_scores']),
                      'response_files': summary['response_files'], 'invalid_scores': len(summary['invalid_scores']),
                      'format_repairs': len(evidence['format_repairs']), 'incomplete_files': summary['incomplete_response_files']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
