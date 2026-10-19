# E-007 — дополнительный post-hoc аудит

Анализ создан **после protocol-lock**, отдельно от предзарегистрированных проверок. Он не менял исходники исполнителя, тесты, ответы или критерии; не вызывал API. Полный перебор подтвердил математическую обратимость конкретных модельных отображений, а не способности модели. Декомпозиция ошибок выполняется только там, где по зафиксированной спецификации есть однозначный независимый декодер. Для C1 универсальный декодер не выдумывается.

Результат полного перебора: `6c027c58af7821bdf810070c44abe3d832c3660f99cd7dec945511ba65d1a3df`. Локальный отчёт: `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e007-001\POSTHOC-PROTOCOL-PROOF.json`.

Декомпозиция: `C:\Users\User\Documents\ChatGPT\ContinuumResearch\artifacts\e007-001\ERROR-DECOMPOSITION.json`; SHA-256 `6ad804f4b86588d3b726c00fac97266478c62e640dd42b08e0963085d315d005`.

Ниже сохранён точный текст проверенных вспомогательных программ для воспроизводимости. Их штатное расположение — `C:/Users/User/Documents/ChatGPT/ContinuumResearch/artifacts/e007-001/`; они импортируют замороженный исследовательский код и читают сохранённые данные, не создают модельных сессий. Сырые данные и сами исполняемые копии остаются вне Git.

## posthoc_protocol_codec_audit.py
SHA-256 исполнявшейся копии: `8fcd9abd36568b982e13dc1c62ac8012f400e5f5916507cb8026dc4efe6da1e3`.

````python
"""Exploratory independent interpretation of the ALREADY LOCKED model specifications.
Not used by workers, training feedback, preregistered scoring or protocol selection.
"""
import base64,hashlib,itertools,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];PROJECT=ROOT/'project';sys.path.insert(0,str(PROJECT))
from research.common import write_json,digest
STUDY=ROOT/'runs/e007-series-001'
FAMILIES=('linear','residue','switch')
FIELDS=('family','a','b','c','e','t','x0','z0','delta')
DOMAINS=(FAMILIES,(-3,-2,2,3),(-2,-1,1,2),tuple(range(-4,5)),(0,-3,-2,2,3),tuple(range(-2,3)),tuple(range(-4,5)),tuple(range(-4,5)),(-9,-7,7,9))
RADICES=(3,4,4,9,5,5,9,9,4)
def encode_p1(rule):
    # Weighted-place construction, not the specification's Horner encoder.
    indices=[d.index(rule[k]) for k,d in zip(FIELDS,DOMAINS)]
    weights=[1166400,291600,72900,8100,1620,324,36,4,1]
    n=sum(i*w for i,w in zip(indices,weights))
    return 'A'+base64.urlsafe_b64encode(n.to_bytes(3,'big')).decode()
def decode_p1(text):
    if not isinstance(text,str) or len(text)!=5 or text[0]!='A' or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in text[1:]):raise ValueError('p1 syntax')
    raw=base64.b64decode(text[1:],altchars=b'-_',validate=True)
    n=int.from_bytes(raw,'big')
    if n>=3499200 or base64.urlsafe_b64encode(raw).decode()!=text[1:]:raise ValueError('p1 canonical/range')
    values=[]
    for domain,radix in zip(reversed(DOMAINS),reversed(RADICES)):
        n,index=divmod(n,radix);values.append(domain[index])
    r=dict(zip(FIELDS,reversed(values)))
    if n or ((r['family']=='linear')!=(r['e']==0)):raise ValueError('p1 family/e')
    return r
def encode_p2(r):
    return 'LRS'[FAMILIES.index(r['family'])]+''.join(str(d.index(r[k])) for k,d in zip(FIELDS[1:],DOMAINS[1:]))
def decode_p2(text):
    if not isinstance(text,str) or len(text)!=9 or text[0] not in 'LRS' or any(c not in '0123456789' for c in text[1:]):raise ValueError('p2 syntax')
    digits=list(map(int,text[1:]))
    if any(i>=len(d) for i,d in zip(digits,DOMAINS[1:])):raise ValueError('p2 range')
    r={'family':FAMILIES['LRS'.index(text[0])]}
    r.update({k:d[i] for k,d,i in zip(FIELDS[1:],DOMAINS[1:],digits)})
    if (r['family']=='linear')!=(r['e']==0):raise ValueError('p2 family/e')
    return r
def full_audit():
    lock=json.loads((STUDY/'protocol-lock.json').read_text());start=time.monotonic();counts={f:0 for f in FAMILIES}
    for family in FAMILIES:
        domains=list(DOMAINS[1:]);domains[3]=(0,) if family=='linear' else (-3,-2,2,3)
        for values in itertools.product(*domains):
            rule=dict(zip(FIELDS,(family,*values)))
            p1,p2=encode_p1(rule),encode_p2(rule)
            assert decode_p1(p1)==rule==decode_p2(p2)
            assert len(json.dumps({'memory':p1}).encode())==19
            assert len(json.dumps({'memory':p2}).encode())==23
            counts[family]+=1
    assert counts=={'linear':233280,'residue':933120,'switch':933120}
    result={'pass':True,'posthoc':True,'scope':'Independent deterministic interpretation of frozen model-proposed formats, not LLM ability or a preregistered superiority endpoint.',
        'protocol_lock_sha256':digest(STUDY/'protocol-lock.json'),'protocol_sha256':{k:v['blob_sha256'] for k,v in lock['versions'].items()},
        'counts':counts,'p1_complete_message_bytes':19,'p2_complete_message_bytes':23,'p1_v1_claimed_bytes':18,'p1_v1_byte_claim_correct':False,
        'wire_semantics_unchanged_across_versions_in_each_line':True,'known_constructions':'p1: mixed-radix rank + standard base64url with prefix; p2: direct positional digit maps, no in-message version/checksum.',
        'novel_coding_method_established':False,'seconds':time.monotonic()-start,'analysis_source_sha256':digest(__file__)}
    write_json(Path(__file__).with_name('POSTHOC-PROTOCOL-PROOF.json'),result);print(json.dumps(result),flush=True)
if __name__=='__main__':full_audit()
````

## supplemental_audit.py
SHA-256 исполнявшейся копии: `1945f77f219c2000dab0db09c466f428b3c6b7a19ca743fef2956adf1c447199`.

````python
"""Supplemental post-hoc error localization and independent execution/accounting census."""
import json,sqlite3,sys
from collections import Counter,defaultdict
from pathlib import Path
ART=Path(__file__).resolve().parent;ROOT=ART.parents[1];PROJECT=ROOT/'project';sys.path.insert(0,str(PROJECT))
from research.common import digest,write_json
from research.e007_audit import rows
from research.e007_codec_audit import independent_fixed
from research.e004_audit import same,calculate
from posthoc_protocol_codec_audit import decode_p1,decode_p2
study=ROOT/'runs/e007-series-001';r=json.loads((study/'report.json').read_text());reg=json.loads((study/'registration.json').read_text())
oracle=json.loads((study/'oracle.json').read_text());worlds={w['id']:w for s in oracle['splits'].values() for w in s}
by_id={x['job']['id']:x for x in r['rows']};decomposition=defaultdict(Counter);details=[]
for row in r['rows']:
 j=row['job']
 if j['role']!='reader' or j['phase']!='test':continue
 label=(j['protocol_version'] if j['condition']=='T2' else j['condition'])+'/'+str(j['budget'])
 source=by_id[j['source']];truth=worlds[j['world']]['rule']
 if not source['audit']['pass'] or source['audit'].get('memory') is None:
  category='writer_failed_or_unsaved'
 elif j['condition']=='C1':category='individual_format_not_formally_decodable_by_this_posthoc_audit'
 else:
  decoder=independent_fixed if j['condition']=='T1' else decode_p1 if j['campaign']=='p1' else decode_p2
  try:decoded=decoder(source['audit']['memory'])
  except (ValueError,IndexError,KeyError):category='writer_invalid_packet';decoded=None
  if decoded is not None:
   answer=row['score']['answer'];rule=answer.get('rule') if isinstance(answer,dict) else None
   writer_correct=same(decoded,truth);reader_matches_wire=same(rule,decoded)
   if not writer_correct:category='writer_wrong_rule_reader_matches_wire' if reader_matches_wire else 'writer_wrong_rule_and_reader_does_not_match_wire'
   elif not reader_matches_wire:category='writer_correct_reader_rule_wrong'
   elif not row['score']['numeric_correct']:category='correct_rule_arithmetic_error'
   else:category='fully_correct'
 decomposition[label][category]+=1
 if category not in ('fully_correct','individual_format_not_formally_decodable_by_this_posthoc_audit'):
  details.append({'reader':j['id'],'writer':j['source'],'world':j['world'],'condition':label,'category':category})
report={'posthoc':True,'scope':'Formal decoders independently transcribed only after protocol lock; never used for worker feedback, protocol selection, primary scoring or inference. C1 arbitrary self-contained text has no universal formal decoder; do not force a favorable classification.',
 'lock_sha256':digest(study/'protocol-lock.json'),'protocol_proof_sha256':digest(ART/'POSTHOC-PROTOCOL-PROOF.json'),'source_sha256':digest(__file__),
 'groups':{k:dict(v) for k,v in decomposition.items()},'nontrivial_cases':details}
write_json(ART/'ERROR-DECOMPOSITION.json',report)
net=rows(study/'provider.jsonl');requests=[e for e in net if e['event']=='request_started'];responses=[e for e in net if e['event']=='response']
with sqlite3.connect((study/'provider-ledger.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
 attempts=db.execute('select id,worker,started,outcome from attempts order by id').fetchall()
assert len(attempts)==len(requests)==len(responses)==2435
assert all(a[3]=='completed' for a in attempts)
assert [a[0] for a in attempts]==[x['attempt'] for x in requests]==[x['attempt'] for x in responses]
prereg=json.loads((ART/'preregistration-commit.json').read_text());execution=json.loads((ART/'command-execution.json').read_text())
assert prereg['no_network_started'] and prereg['at']<execution['started_at']<min(a[2] for a in attempts)
assert execution['exit_status']==0 and execution['stderr']==''
assert r['terminal'] and r['model_positions']==984 and r['lineage_verified_contexts']==980
executed=0;exceptions=[]
for j in reg['schedule']:
 unit=study/'units'/j['id'];result=json.loads((unit/'result.json').read_text())
 if (unit/'supervisor/session.jsonl').exists():
  events=rows(unit/'supervisor/session.jsonl');commands=[e for e in events if e.get('event')=='command_execution']
  assert len(commands)==1;executed+=1
 if result['status'] in ('failed','budget_rejected','skipped_dependency'):
  exceptions.append({k:result.get(k) for k in ('job','status','failure_type','failure','exit_status','save_attempts')})
assert executed==983
writers=[x for x in r['rows'] if x['job']['role']=='writer'];second_attempts=sum(json.loads((study/'units'/x['job']['id']/'result.json').read_text()).get('save_attempts')==2 for x in writers)
models=dict(Counter(e['response']['model'] for e in responses))
cross={p:{k:sum(x['score'][k] for x in r['rows'] if x['job'].get('control')=='cross_model' and x['job']['campaign']==p) for k in ('rule_correct','numeric_correct','arithmetic_error_with_correct_rule')} for p in ('p1','p2')}
audit={'pass':True,'preregistration_commit':prereg['commit'],'preregistration_commit_record_at':prereg['at'],'command_started_at':execution['started_at'],
 'first_reserved_API_at':min(a[2] for a in attempts),'exit_status':0,'literal_stderr':'','live_seconds':execution['finished_at']-execution['started_at'],
 'positions':991,'model_positions':984,'actual_isolated_model_containers':983,'full_success_or_rejection_or_injected_crash_lineages_verified':980,
 'failed_tool_protocol_contexts':3,'dependent_skips':1,'API_attempts':len(attempts),'API_responses':len(responses),'API_failed_or_unknown':0,
 'returned_models':models,'smoke_contexts':2,'worker_retries':0,'writer_second_attempts':second_attempts,
 'cross_model_by_line':cross,'exceptions':exceptions,'known_concurrency':1,'recovery_file_present':(study/'recovery.jsonl').exists(),
 'registration_sha256':digest(study/'registration.json'),'raw_report_sha256':digest(study/'report.json')}
write_json(ART/'EXECUTION-AUDIT.json',audit)
print(json.dumps({'execution':audit,'posthoc_groups':report['groups'],'nontrivial_cases':details}),flush=True)
````
