import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.resolve_researched_source_gaps import validate_item,load_plan,digest

class SourceGapResearchGuards(unittest.TestCase):
    def deferred(self):
        return {'target_id':'lemma:11932','action':'defer','confidence':.8,'reason':'Insufficient linked evidence.#aigc','author':'B','reviewer':'C','evidence':[{'url':'https://example.org/source'}],'payload':None}
    def restored(self):
        x=self.deferred();x['action']='restore_lemma';x['payload']={k:'Meaning#aigc' for k in ['definition_nl','usage_note','gloss_en','explanation_en','explanation_zh','example_nl','example_zh']}
        x['payload'].update(gloss_zh='角色名#aigc',pos='PROPN');return x
    def test_self_review_is_rejected(self):
        x=self.restored();x['reviewer']=x['author']
        with self.assertRaises(AssertionError):validate_item(x)
    def test_deferred_item_cannot_hide_mutation(self):
        x=self.deferred();x['payload']={'definition_nl':'Unexpected mutation#aigc'}
        with self.assertRaises(AssertionError):validate_item(x)
    def test_foreign_only_chinese_gloss_is_rejected(self):
        x=self.restored();x['payload']['gloss_zh']='Piften#aigc'
        with self.assertRaises(AssertionError):validate_item(x)
    def test_restoration_cannot_target_a_relation(self):
        x=self.restored();x['target_id']='relation:1'
        with self.assertRaises(AssertionError):validate_item(x)
    def test_canonical_name_must_match_normalized_key(self):
        x=self.restored();x['payload']['canonical_repair']={'old_lemma_norm':'lzen','new_lemma_norm':'lzen','new_lemma':'lsd'}
        with self.assertRaises(AssertionError):validate_item(x)

class ResearchRoundCoverageGuards(unittest.TestCase):
    def make_round(self,root,count=8):
        targets=[f'lemma:{i}' for i in range(1,count+1)]
        context={'held_lemmas':[{'lemma':{'id':i}} for i in range(1,count+1)],'relations':[],'new_senses':[]}
        (root/'context.json').write_text(json.dumps(context))
        plan={'embedding_enabled':False,'human_reviewed':False,'proofs':[],'items':[]}
        for offset,(author,reviewer) in enumerate([('A','B'),('B','C'),('C','A')]):
            items=[{'target_id':target,'disposition':'defer','sense':None,'confidence':.8,
                    'reason':'No record-specific evidence.#aigc','evidence':[{'title':'Original source'}]}
                   for i,target in enumerate(targets) if i%3==offset]
            candidate=root/f'proposals-{author}.json';candidate.write_text(json.dumps({'author':author,'items':items}))
            candidate_sha=hashlib.sha256(candidate.read_bytes()).hexdigest()
            decisions=[{'target_id':x['target_id'],'verdict':'approve','reason':'Independent review concurs.#aigc'} for x in items]
            review=root/f'review-{reviewer}-of-{author}.json';review.write_text(json.dumps({'reviewer':reviewer,'candidate_sha256':candidate_sha,'decisions':decisions}))
            plan['proofs'].append({'author':author,'candidate':candidate.name,'candidate_sha256':candidate_sha,
                                   'review':review.name,'review_sha256':hashlib.sha256(review.read_bytes()).hexdigest()})
            plan['items'].extend({'target_id':x['target_id'],'author':author,'reviewer':reviewer,
                'reviewed_item_sha256':digest(x),'action':'defer','payload':None,
                'confidence':x['confidence'],'reason':x['reason'],'evidence':x['evidence']} for x in items)
        (root/'approved-plan.json').write_text(json.dumps(plan));return plan

    def test_smaller_residual_round_keeps_exact_source_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.make_round(root)
            self.assertEqual(len(load_plan(root)['items']),8)

    def test_smaller_round_cannot_silently_omit_a_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan=self.make_round(root);plan['items'].pop()
            (root/'approved-plan.json').write_text(json.dumps(plan))
            with self.assertRaises(AssertionError):load_plan(root)

    def test_empty_source_context_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.make_round(root,0)
            with self.assertRaises(AssertionError):load_plan(root)

if __name__=='__main__':unittest.main()
