"""Original bytes, codec choice and explicit cached repairs stay traceable."""
import codecs
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from finmy.search.decoding import decode_source
from finmy.search.handoff import assemble_sources
from finmy.search.sources import (SourceStore, document_is_usable, fetch_public,
                                  parse_document, repair_saved_sources)
from finmy.search.state import SearchConfig, SearchState, digest, write_json


class SearchDecodingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = SearchState(self.root, 'case', task={
            'target_type': 'event', 'target_name': 'Investment',
            'query_text': 'Reconstruct investment', 'key_words': []})
        self.store = SourceStore(self.state)

    def save(self, raw, kind='html', encoding='ISO-8859-1'):
        sid = self.store.register('https://example.test/report')
        return sid, self.store.save_raw(sid, raw, kind, encoding)

    def test_html_utf8_meta_overrides_latin1_http_default_and_preserves_unicode(self):
        body = '<html><head><meta charset="utf-8"></head><body><p>巴菲特增持日本商社。é £ ¥</p></body></html>'
        sid, doc = self.save(body.encode('utf-8'))
        self.assertEqual(doc['encoding'], 'utf-8')
        self.assertEqual(doc['encoding_decision'], 'html_meta')
        self.assertIn('巴菲特增持日本商社。é £ ¥', [b['text'] for b in doc['blocks']])
        self.assertTrue(document_is_usable(doc))
        self.assertEqual(self.store.document(sid), doc)

    def test_bom_precedes_conflicting_declarations(self):
        body = '<meta charset="gb2312"><p>投资完成。</p>'
        text, encoding, reason = decode_source(codecs.BOM_UTF8 + body.encode(), 'html', 'cp1252')
        self.assertEqual(text, body)
        self.assertEqual((encoding, reason), ('utf-8-sig', 'byte_order_mark'))
        text, encoding, _ = decode_source('投资完成。'.encode('utf-16'), 'txt', 'ISO-8859-1')
        self.assertEqual(text, '投资完成。')
        self.assertEqual(encoding, 'utf-16')

    def test_xml_and_meta_http_equiv_and_gb18030_are_supported(self):
        values = [
            ('<?xml version="1.0" encoding="gb2312"?><p>投资完成。</p>', 'xml_declaration'),
            ('<head><meta http-equiv="Content-Type" content="text/html; charset=gbk"></head><p>投资完成。</p>', 'html_meta')]
        for body, reason in values:
            text, encoding, actual_reason = decode_source(body.encode('gb18030'), 'html', 'ISO-8859-1')
            self.assertEqual((text, encoding, actual_reason), (body, 'gb18030', reason))

    def test_non_declared_utf8_gb18030_and_real_latin1_remain_readable(self):
        self.assertEqual(decode_source('投资完成。'.encode(), 'txt', 'ISO-8859-1')[0], '投资完成。')
        self.assertEqual(decode_source('投资完成。'.encode('gb18030'), 'txt')[0], '投资完成。')
        self.assertEqual(decode_source(b'Le caf\xe9 est ouvert.', 'txt', 'ISO-8859-1')[0], 'Le café est ouvert.')
        self.assertEqual(decode_source(b'Price \x80 20.', 'txt', 'windows-1252')[0], 'Price € 20.')

    def test_charset_words_in_scripts_comments_and_footer_are_not_declarations(self):
        body = '<head><!-- <meta charset="cp1252"> --><script>var x="<meta charset=cp1252>";</script>' \
               '<meta name="description" content="charset=cp1252 is outdated">' \
               '<meta charset=utf-8></head><p>交易已完成。</p><footer><meta charset=gb2312></footer>'
        text, encoding, _ = decode_source(body.encode(), 'html', 'ISO-8859-1')
        self.assertEqual(text, body)
        self.assertEqual(encoding, 'utf-8')

    def test_invalid_bytes_are_not_lossily_accepted(self):
        with self.assertRaises(UnicodeError):
            decode_source(b'\x81', 'txt')
        self.assertEqual(decode_source('有效文本'.encode(), 'txt', 'base64_codec')[0], '有效文本')

    def test_fetch_uses_only_explicit_header_charset(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.is_redirect = False
        response.encoding = 'ISO-8859-1'  # requests' default, not a server declaration.
        response.iter_content.return_value = [b'<p>Short news.</p>']
        config = SearchConfig(allow_network=True)
        with patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('8.8.8.8', 443))]), \
                patch('requests.get', return_value=response):
            for header, expected in [('text/html', None), ('text/html; charset="GBK"', 'gbk')]:
                response.headers = {'Content-Type': header}
                self.assertEqual(fetch_public('https://example.test/report', config)[2], expected)

    def test_body_checks_allow_short_news_but_reject_explicit_challenge_shells(self):
        for body in ('<p>Deal closed.</p>', '<h1>Company addresses CAPTCHA failures</h1><p>The deal closed.</p>',
                     '<div>Sign in</div><p>The deal closed.</p>'):
            blocks = parse_document(body.encode(), 'html')
            self.assertTrue(document_is_usable({'status': 'success', 'kind': 'html', 'blocks': blocks}))
        for body in ('<h1>Client Challenge</h1><p>A required part of this site couldn’t load.</p>',
                     '<h1>环境异常</h1><p>当前环境异常，完成验证后即可继续访问。</p>',
                     '<h1>Sign in</h1><p>Email</p><p>Password</p><p>Forgot password?</p>'):
            sid = self.store.register('https://example.test/' + digest(body)[:8])
            doc = self.store.save_raw(sid, body.encode(), 'html')
            self.assertEqual(doc['status'], 'blocked')
            self.assertFalse(document_is_usable(doc))

    def legacy_garbled(self):
        raw = '<html><head><meta charset="utf-8"></head><p>巴菲特增持日本商社。</p></html>'.encode()
        sid, doc = self.save(raw)
        folder = self.state.root / 'sources' / sid / doc['version']
        legacy = {**doc, 'encoding': 'ISO-8859-1', 'parser_version': 'search-v1',
                  'blocks': [{'paragraph': 1, 'text': '巴菲特增持日本商社。'.encode().decode('latin1')}]}
        for key in ('supplied_encoding', 'encoding_decision'):
            legacy.pop(key, None)
        write_json(folder / 'parsed.json', legacy)
        self.state.data['sources'][sid]['parsed_hashes'][doc['version']] = digest((folder / 'parsed.json').read_bytes())
        self.state.save()
        self.store.read(sid)
        assemble_sources(self.state, [sid], gaps=['Partial chronology'], reason='supported')
        self.state.data['status'] = 'finished'
        self.state.save()
        return sid, folder, raw, legacy

    def test_explicit_repair_preserves_raw_counts_and_archives_old_interpretation(self):
        sid, folder, raw, old = self.legacy_garbled()
        self.state.data['pending_finish_repair'] = {'source_ids': [sid], 'gaps': [], 'model_call': 3}
        self.state.data['invalid_actions'] = 2
        write_json(self.state.run_dir / 'handoff_repair.json', {'retained_source_ids': [sid]})
        before = copy.deepcopy(self.state.data)
        active_manifest = json.loads((self.state.run_dir / 'complete_material.json').read_text())
        with patch('finmy.search.sources.fetch_public', side_effect=AssertionError('No network')):
            changed = repair_saved_sources(self.state)
        self.assertEqual(changed, [sid])
        self.assertEqual((folder / 'raw').read_bytes(), raw)
        self.assertEqual(self.state.data['usage'], before['usage'])
        self.assertEqual(self.state.data['read_sources'], before['read_sources'])
        self.assertEqual(self.state.data['sources'][sid]['version'], digest(raw))
        self.assertEqual(self.state.data['sources'][sid]['read_ranges'], [])
        self.assertEqual(self.state.data['status'], 'ready')
        self.assertNotIn('pending_finish_repair', self.state.data)
        self.assertEqual(self.state.data['invalid_actions'], 0)
        self.assertFalse((self.state.run_dir / 'handoff_repair.json').exists())
        self.assertEqual(self.store.document(sid)['encoding'], 'utf-8')
        self.assertFalse((self.state.run_dir / 'complete_material.json').exists())
        archive = next((self.state.run_dir / 'parse_repairs').iterdir())
        self.assertEqual(json.loads((archive / 'handoff_repair.json').read_text()), {'retained_source_ids': [sid]})
        self.assertEqual(json.loads((archive / 'complete_material.json').read_text()), active_manifest)
        previous_hash = before['sources'][sid]['parsed_hashes'][digest(raw)]
        self.assertEqual(json.loads((folder / 'parsed_revisions' / (previous_hash + '.json')).read_text()), old)
        self.assertEqual(self.state.data['sources'][sid]['parse_history'][-1]['read_ranges'], before['sources'][sid]['read_ranges'])
        with self.assertRaises(ValueError):
            assemble_sources(self.state, [sid], reason='supported')
        self.store.read(sid)
        payload = assemble_sources(self.state, [sid], reason='supported')
        self.assertIn('巴菲特增持日本商社。', payload['samples'][0]['content'])
        self.assertEqual(repair_saved_sources(self.state), [])

    def test_document_reads_are_readonly_and_healthy_saved_documents_do_not_reopen(self):
        sid, folder, raw, old = self.legacy_garbled()
        stored = (folder / 'parsed.json').read_bytes()
        self.assertEqual(self.store.document(sid), old)
        self.assertEqual((folder / 'parsed.json').read_bytes(), stored)
        repair_saved_sources(self.state)
        self.store.read(sid)
        assemble_sources(self.state, [sid], reason='supported')
        self.state.data['status'] = 'finished'
        self.state.save()
        before = copy.deepcopy(self.state.data)
        self.assertEqual(repair_saved_sources(self.state), [])
        self.assertEqual(self.state.data, before)

    def test_repeat_save_returns_existing_persisted_parse_not_a_different_unsaved_parse(self):
        sid, folder, raw, old = self.legacy_garbled()
        doc = self.store.save_raw(sid, raw, 'html', 'utf-8')
        self.assertEqual(doc, old)
        self.assertEqual(self.store.document(sid), old)

    def test_repair_refuses_tampered_source_bytes(self):
        sid, folder, raw, old = self.legacy_garbled()
        (folder / 'raw').write_bytes(raw + b'tampered')
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            repair_saved_sources(self.state)


if __name__ == '__main__':
    unittest.main()
