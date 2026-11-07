import unittest
from finmy.builder.json_response import parse_json_response as parse

class JsonResponseTests(unittest.TestCase):
    def test_valid_fenced_and_prose(self):
        for text in ('{"a": [1, 2]}', '```json\n{"a": [1, 2]}\n```', 'Result: {"a": [1, 2]} Done.'):
            self.assertEqual(parse(text), {"a": [1, 2]})

    def test_missing_and_trailing_commas(self):
        self.assertEqual(parse('{"a": 1 "b": [{"x": 2} {"x": 3},],}'),
                         {"a": 1, "b": [{"x": 2}, {"x": 3}]})

    def test_evidence_is_unchanged(self):
        import json
        quote = 'He said "yes", then wrote {x}, [y]. 中文，原文。'
        text = '{"quote": ' + json.dumps(quote) + ' "ok": true}'
        self.assertEqual(parse(text), {"quote": quote, "ok": True})

    def test_truncation_does_not_accept_inner_fragment(self):
        for text in ('{"events": [{"id": 1}', '{"quote": "unfinished', '{"a": [1}'): 
            with self.assertRaises(ValueError):
                parse(text)

    def test_no_fabrication_of_values(self):
        for text in ('{"value": }', '{"value": unknown}', 'No JSON', '{"x" 1}'):
            with self.assertRaises(ValueError):
                parse(text)

if __name__ == '__main__':
    unittest.main()

class JsonRetryTests(unittest.TestCase):
    def completion(self, responses):
        import ast
        import json
        from pathlib import Path
        from types import SimpleNamespace
        source = Path('finmy/builder/agent_build/main_build.py').read_text()
        method = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == '_run_subject')
        complete = next(n for n in method.body if isinstance(n, ast.FunctionDef) and n.name == 'complete')
        requests, traces = [], []
        iterator = iter(responses)
        def infer(*args, **kwargs):
            requests.append(kwargs['payload'])
            value = next(iterator)
            return SimpleNamespace(response=value, to_dict=lambda: {'response': value})
        ns = {'json': json, 'calls': [], 'extract_json_response': parse,
              'run_single_inference': infer, 'InferInput': lambda **kw: kw,
              'self': SimpleNamespace(agents_lm=None, save_traces=lambda *args: traces.append(args))}
        exec(compile(ast.Module(body=[complete], type_ignores=[]), '<complete>', 'exec'), ns)
        return ns['complete'], requests, traces

    def test_retries_complete_response_once(self):
        complete, requests, traces = self.completion(['{"a": [', '{"a": [1]}'])
        self.assertEqual(complete('Builder', 'system', {'source': 'original'}), {'a': [1]})
        self.assertEqual(len(requests), 2)
        self.assertIn('original', requests[1])
        self.assertTrue(any('json-error' in row[1] for row in traces))

    def test_retry_is_bounded(self):
        complete, requests, traces = self.completion(['{"a": [', '{"a": ['])
        with self.assertRaisesRegex(ValueError, 'after one retry'):
            complete('Builder', 'system', {})
        self.assertEqual(len(requests), 2)
