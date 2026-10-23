import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.repair_bilingual_gaps import prepare, validate_row


class ReviewedBilingualRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for folder in ['chunks/0001','ready','reviews']:(self.root/folder).mkdir(parents=True)
        self.source={'sense_id':1,'snapshot_hash':'source-hash'}
        self.row={**self.source,'decision':'correct','translations':{
          'zh':{'gloss':'向上#aigc','explanation':'朝更高位置移动。#aigc'},
          'en':{'gloss':'up#aigc','explanation':'Towards a higher position.#aigc'}},'confidence':.8,'reason':'Replaces untranslated omhoog.#aigc'}
        self.job={'chunk':'0001','author':'A','reviewer':'B','count':1}
        self.write('chunks/0001/input.jsonl',json.dumps(self.source)+'\n')
        self.write('chunks/0001/output.jsonl',json.dumps(self.row)+'\n')
        sha=hashlib.sha256((self.root/'chunks/0001/output.jsonl').read_bytes()).hexdigest()
        self.ready={'author':'A','chunk':'0001','count':1,'output_sha256':sha}
        self.review={'reviewer':'B','author':'A','chunk':'0001','reviewed_count':1,'output_sha256':sha,
         'decisions':[{'sense_id':1,'verdict':'approve','reason':'Both languages express the upward direction.#aigc'}]}
        self.publish()

    def write(self,name,data):
        (self.root/name).write_text(data)

    def publish(self):
        self.write('ready/author-A-0001.json',json.dumps(self.ready))
        self.write('reviews/review-B-0001.json',json.dumps(self.review))

    def test_independent_review_returns_same_authored_meaning(self):
        result,provenance=prepare(self.root,self.job)
        self.assertEqual(result,[self.row]);self.assertFalse(provenance['human_reviewed'])

    def test_published_authorship_change_is_detected(self):
        self.write('chunks/0001/output.jsonl',json.dumps({**self.row,'reason':'Different.#aigc'})+'\n')
        with self.assertRaises(ValueError):prepare(self.root,self.job)

    def test_missing_or_self_review_is_rejected(self):
        self.review['decisions']=[];self.publish()
        with self.assertRaises(ValueError):prepare(self.root,self.job)
        self.review['decisions']=[{'sense_id':1,'verdict':'approve','reason':'Checked.#aigc'}]
        self.review['reviewer']='A';self.publish()
        with self.assertRaises(ValueError):prepare(self.root,self.job)

    def test_reviewer_replacement_has_to_match_input(self):
        self.review['decisions']=[{'sense_id':1,'verdict':'replace','reason':'Fix meaning.#aigc','replacement':{**self.row,'sense_id':2}}];self.publish()
        with self.assertRaises(ValueError):prepare(self.root,self.job)

    def test_copied_foreign_chinese_gloss_is_rejected(self):
        row=copy.deepcopy(self.row);row['translations']['zh']['gloss']='omhoog#aigc'
        with self.assertRaises(ValueError):validate_row(row,self.source)

    def test_blocked_cannot_smuggle_translation_or_changed_snapshot(self):
        row={**self.row,'decision':'blocked'}
        with self.assertRaises(ValueError):validate_row(row,self.source)
        row['translations']=None;validate_row(row,self.source)
        row['snapshot_hash']='changed'
        with self.assertRaises(ValueError):validate_row(row,self.source)
