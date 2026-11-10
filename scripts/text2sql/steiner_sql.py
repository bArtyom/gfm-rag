"""Frozen SQL prompt/cohort preparation; no label fields enter model inputs."""
import hashlib
import json
from collections import defaultdict

ARMS=['full','unit','weighted']


def payload_key(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def make_messages(row,schema):
    return [{'role':'system','content':'You are an expert SQLite developer. Write exactly one SQLite SELECT query that answers the question using the given schema and evidence. Output SQL only, without explanation or markdown.'},
        {'role':'user','content':'# Database schema\n'+schema+'\n\n# Evidence\n'+(row.get('evidence') or '(none)')+'\n\n# Question\n'+row['question']+'\n\n# SQL\n'}]


def choose_pilot(rows,count):
    groups=defaultdict(list)
    for r in rows:
        groups[r['db_id']].append(r)
    for db in groups:
        groups[db].sort(key=lambda r:hashlib.sha256(f'20261110:steiner-sql:{db}:{r["question_id"]}'.encode()).hexdigest())
    selected=[]
    while len(selected)<min(count,len(rows)):
        for db in sorted(groups):
            if groups[db] and len(selected)<count:
                selected.append(groups[db].pop(0))
    return selected
