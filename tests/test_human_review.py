import unittest
from scripts.apply_human_review import assert_expected, validate_action


class HumanReviewTests(unittest.TestCase):
    def test_changed_live_record_is_not_overwritten(self):
        assert_expected({'gloss':'old','lang':'en'},{'gloss':'old'})
        with self.assertRaises(ValueError):
            assert_expected({'gloss':'new'},{'gloss':'old'})
        with self.assertRaises(ValueError):
            assert_expected(None,{'gloss':'old'})

    def test_manifest_cannot_merge_delete_or_change_pos(self):
        action={'table':'senses','id':1,'expected':{'usage_note':'old'},'evidence':{'document':'review'},'values':{'usage_note':None}}
        validate_action(action)
        for values in ({'merged_into_sense_id':2},{'lemma_pos_entry_id':3},{'review_status':'rejected'}):
            with self.assertRaises(ValueError):validate_action({**action,'values':values})

    def test_translation_requires_evidence_and_review_origin(self):
        action={'table':'sense_translations','id':1,'expected':{'lang':'en','gloss':'old'},
                'values':{'gloss':'new','explanation':'A new meaning'},'decision':'review_guided','evidence':{'document':'review'}}
        validate_action(action)
        for override in ({'evidence':{}},{'decision':'accepted'},{'values':{'gloss':'new'}}):
            with self.assertRaises(ValueError):validate_action({**action,**override})
