import unittest
import hashlib
import json
from pathlib import Path
import tempfile

from scripts.apply_english_source_repairs import effective_proposals, validate_proposal


class RepairProposalTests(unittest.TestCase):
    def test_reject_mapping_requires_identifiable_evidence(self):
        row={'sense_id':1,'action':'reject_mapping','reason':'Wrong POS.#aigc','evidence':'The source describes a noun for a verb entry.#aigc'}
        validate_proposal(row)
        for field,value in [('sense_id',True),('action','delete'),('evidence','')]:
            with self.assertRaises(ValueError):validate_proposal({**row,field:value})

    def test_partial_correction_and_invalid_pos_or_confidence_rejected(self):
        row={'sense_id':1,'action':'correct','definition_nl':'Niet uitgewerkte afkorting.#aigc',
             'usage_note':'Niet uitbreiden zonder context.#aigc','gloss_en':'unexpanded abbreviation#aigc',
             'explanation_en':'The source does not give the full form.#aigc','gloss_zh':'未展开的缩写#aigc',
             'pos':'ABBR','confidence':.5,'reason':'Keep uncertainty.#aigc','evidence':'No expansion in source.#aigc'}
        validate_proposal(row)
        for field,value in [('gloss_en','unknown'),('pos','garbage'),('confidence',float('nan')),('preserve_external_synset','yes')]:
            with self.assertRaises(ValueError):validate_proposal({**row,field:value})

    def test_retraction_is_scoped_to_exact_review_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/'review-C.json'
            review={'source_repairs':[{'sense_id':1},{'sense_id':2}]}
            path.write_text(json.dumps(review))
            original=path.read_bytes()
            entry={'review':path.name,'review_sha256':hashlib.sha256(original).hexdigest(),
                   'sense_id':1,'reason':'Independent evidence restores this sense.#aigc'}
            (root/'source-repair-retractions.json').write_text(json.dumps({'retractions':[entry]}))
            proposals,retracted=effective_proposals(root,path,review)
            self.assertEqual(proposals,[{'sense_id':2}])
            self.assertEqual(retracted,[entry])
            self.assertEqual(path.read_bytes(),original)
            path.write_text(json.dumps(review)+'\n')
            with self.assertRaisesRegex(ValueError,'hash changed'):
                effective_proposals(root,path,review)
