import json
from pathlib import Path
import tempfile
import unittest

from scripts.complete_english_translations import input_hash, validate_chunk, write_jsonl, write_json, apply_reviews


class EnglishCompletionValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.source={'sense_id':1,'lemma':'huis','level':1,'pos':'NOUN',
                     'definition_nl':'gebouw om in te wonen','usage_note':'',
                     'source_key':'test','gloss_zh':'房屋','example_nl':'Dit is mijn huis.'}
        self.source['input_hash']=input_hash(self.source)
        self.row={'sense_id':1,'input_hash':self.source['input_hash'],'status':'draft',
                  'gloss':'house#aigc','explanation':'A building in which people live.#aigc',
                  'confidence':.8,'quality_note':'Clear residential sense.#aigc'}
        write_jsonl(self.directory/'input.jsonl',[self.source])

    def validate(self,rows=None):
        write_jsonl(self.directory/'output.jsonl',rows if rows is not None else [self.row])
        return validate_chunk(self.directory)

    def test_valid_draft_and_preserved_snapshot(self):
        inputs,outputs=self.validate()
        self.assertEqual(outputs[0]['gloss'],'house#aigc')
        self.assertEqual(input_hash(inputs[0]),self.row['input_hash'])

    def test_missing_row_and_unknown_ids_rejected(self):
        with self.assertRaisesRegex(ValueError,'incomplete'): self.validate([])
        self.row['sense_id']=99
        with self.assertRaisesRegex(ValueError,'sense_id'):self.validate()

    def test_changed_source_rejected(self):
        self.source['definition_nl']='a different definition'
        write_jsonl(self.directory/'input.jsonl',[self.source])
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.validate()

    def test_invalid_marker_language_and_confidence_rejected(self):
        original=dict(self.row)
        for field,value in [('gloss','house'),('explanation','房屋#aigc'),
                            ('confidence',float('nan')),('confidence',True),
                            ('gloss','\tbad#aigc')]:
            self.row={**original,field:value}
            with self.assertRaises(ValueError):self.validate()

    def test_blocked_cannot_smuggle_translation(self):
        self.row.update(status='blocked',confidence=.3)
        with self.assertRaisesRegex(ValueError,'blocked'):self.validate()
        self.row.update(gloss='',explanation='')
        self.validate()
        self.row['confidence']=.8
        with self.assertRaisesRegex(ValueError,'blocked'):self.validate()

    def test_duplicate_ids_rejected_with_matching_row_count(self):
        second={**self.source,'sense_id':2}
        second['input_hash']=input_hash(second)
        write_jsonl(self.directory/'input.jsonl',[self.source,second])
        with self.assertRaisesRegex(ValueError,'duplicate'):self.validate([self.row,self.row])


class ReviewApplicationTests(unittest.TestCase):
    setUp = EnglishCompletionValidationTests.setUp
    validate = EnglishCompletionValidationTests.validate
    def test_invalid_review_never_changes_original_output(self):
        self.validate()
        original=(self.directory/'output.jsonl').read_bytes()
        write_json(self.directory/'reviews'/'invalid.json',{
            'reviewed_chunks':[self.directory.name],'reviewed_count':1,
            'corrections':[{'chunk':self.directory.name,'sense_id':1,'reason':'test',
                            'fields':{'sense_id':2}}]})
        with self.assertRaisesRegex(ValueError,'identity/hash'):
            apply_reviews(self.directory,[self.directory],['invalid.json'])
        self.assertEqual((self.directory/'output.jsonl').read_bytes(),original)

    def test_review_preserves_original_and_saves_valid_correction(self):
        self.validate()
        original=(self.directory/'output.jsonl').read_bytes()
        write_json(self.directory/'reviews'/'valid.json',{
            'reviewed_chunks':[self.directory.name],'reviewed_count':1,
            'corrections':[{'chunk':self.directory.name,'sense_id':1,'reason':'narrower meaning',
                            'fields':{'confidence':.6,'quality_note':'Needs source review.#aigc'}}]})
        result=apply_reviews(self.directory,[self.directory],['valid.json'])
        self.assertEqual(result['corrections_count'],1)
        self.assertEqual((self.directory/'output.pre-review.jsonl').read_bytes(),original)
        self.assertEqual(validate_chunk(self.directory)[1][0]['confidence'],.6)


if __name__=='__main__':unittest.main()
