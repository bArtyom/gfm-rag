import sys
from pathlib import Path
import unittest
import hashlib
import tempfile
import subprocess
import time
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/text2sql'))
from steiner_sql import make_messages, payload_key, choose_pilot
from steiner_sql_runtime import read_reference_rows,session_members,stop_owned_session


class SteinerSQLTests(unittest.TestCase):
    def test_prompt_scope_and_identical_evidence(self):
        row={'question':'Which students enrolled?', 'evidence':'CS means computer science.', 'SQL':'PRIVATE_REFERENCE'}
        a=make_messages(row,'CREATE TABLE students(id number);')
        b=make_messages(row,'CREATE TABLE courses(id number);')
        self.assertNotIn('PRIVATE_REFERENCE',str(a))
        self.assertIn(row['evidence'],str(a))
        self.assertIn(row['evidence'],str(b))
        self.assertEqual(a[0],b[0])

    def test_payload_cache_is_exact_not_just_question_identity(self):
        a={'model':'local7b','messages':make_messages({'question':'q','evidence':''},'schema'),'temperature':0}
        b={'temperature':0,'messages':a['messages'],'model':'local7b'}
        self.assertEqual(payload_key(a),payload_key(b))
        self.assertNotEqual(payload_key(a),payload_key({**a,'model':'another'}))
        self.assertNotEqual(payload_key(a),payload_key({**a,'temperature':1}))

    def test_sampling_is_order_independent_and_ignores_labels(self):
        rows=[{'db_id':str(i%4),'question_id':i,'SQL':'irrelevant'} for i in range(120)]
        ids=lambda xs:{(r['db_id'],r['question_id']) for r in xs}
        self.assertEqual(ids(choose_pilot(rows,100)),ids(choose_pilot(list(reversed(rows)),100)))
        self.assertEqual(len(ids(choose_pilot(rows,100))),100)

    def test_reference_bytes_must_match_frozen_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'dev.json';path.write_text('[]')
            cfg={'dataset_root':directory,'questions_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertEqual(read_reference_rows(cfg),[])
            path.write_text('[{}]')
            with self.assertRaises(ValueError):read_reference_rows(cfg)

    def test_cleanup_reaps_owned_session_but_not_unrelated_process(self):
        owned=subprocess.Popen(['sh','-c','(trap "" TERM; sleep 30) & wait'],start_new_session=True)
        unrelated=subprocess.Popen(['sleep','30'],start_new_session=True)
        try:
            time.sleep(.1)
            members=session_members(owned.pid)
            self.assertIn(owned.pid,members)
            result=stop_owned_session(owned,timeout=.2)
            self.assertTrue(result['all_owned_processes_exited'])
            self.assertIsNone(unrelated.poll())
        finally:
            if owned.poll() is None:owned.kill();owned.wait()
            unrelated.terminate();unrelated.wait()


if __name__=='__main__':
    unittest.main()
