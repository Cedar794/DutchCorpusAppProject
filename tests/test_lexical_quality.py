import unittest
from lexicon_search.quality import translation_signals, translation_blockers
from scripts.audit_lexical_quality import audit
from scripts.validate_sense_translations import validate_record


class LexicalQualityTests(unittest.TestCase):
    def test_corruption_blocks_but_quoted_grammar_does_not(self):
        self.assertEqual(translation_blockers('zh', '{\\fnArial}你', '你'), ['format_residue'])
        self.assertEqual(translation_blockers('zh', '你的（jouw 的非重读形式）', '用于表示所属。'), [])
        self.assertIn('grammar_only_gloss', translation_signals('zh', '及物动词'))
        self.assertNotIn('grammar_only_gloss', translation_signals('zh', '穿透（及物动词）'))

    def test_short_gloss_is_not_automatically_truncated(self):
        self.assertEqual(translation_signals('en', 'be'), [])
        self.assertIn('possible_incomplete_gloss', translation_signals('en', 'the presence of'))
        self.assertEqual(translation_blockers('en', 'be able to'), [])

    def test_validator_quarantines_missing_source_and_formatting(self):
        self.assertIsNotNone(validate_record({'sense_id':1,'needs_source_review':True}))
        self.assertEqual(validate_record({'sense_id':1,'lang':'zh','gloss':'{\\fs12}你','explanation':'你'}), 'format_residue')

    def test_duplicate_signal_respects_lemma_pos_domain_register(self):
        base = dict(lemma_id=1, lemma='x', pos='NOUN', domain=None, register=None,
                    definition_nl='iets', display_definition_nl=None, usage_note=None)
        senses = [dict(base,sense_id=1), dict(base,sense_id=2), dict(base,sense_id=3,pos='VERB'),
                  dict(base,sense_id=4,register='vulgar')]
        result = audit({'senses':senses,'translations':[],'examples':[]})
        self.assertEqual(result['duplicate_groups'], [[1,2]])
        self.assertEqual(len(senses),4)
