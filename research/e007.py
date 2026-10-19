"""E007 serial durable controller: development first, immutable protocol lock, then test."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import time
from .common import PROJECT, ROOT, digest, runtime_identity, write_json
from .e002 import smoke
from .e003 import Jobs, copy_database, implementation_hashes, job_id
from .e004 import transient
from .e005 import recover
from .e007_archive import Archive, canonical
from .e007_audit import audit, score, snapshot
from .e007_codec import FIXED_SPEC, bounds
from .e007_execute import execute
from .e007_protocol import corpus, schedule
from .profiles import create_worker
from .responses_provider import SpendLedger
from .e007_provider import MeasuredProvider
from .sandbox import image_id, isolation_probe


def make_unit(path):
    for part in ('supervisor','state','workers'):
        (path/part).mkdir(parents=True,exist_ok=True)


def archive_write(run, operation):
    make_unit(run)
    with (run/'supervisor/archive.jsonl').open('x',encoding='utf-8') as log:
        bridge = Archive(run,'host',[],log,'registered-deterministic-controller')
        try:
            return operation(bridge)
        finally:
            bridge.close()


def preregistration(inputs, jobs, fixture):
    return {
        'experiment':'E-007','fixture':fixture,'registered_at_utc':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        'design':'Emergent Shared Protocol: independent proposers, writers, readers and critics communicate through real Continuum; no model-supplied code executes.',
        'sample':{'training_worlds':6,'validation_worlds':9,'test_worlds':24,'families':['linear','residue','switch'],
                  'budgets_bytes':[24,32,48],'protocol_campaigns':2,'versions_per_campaign':3,
                  'model_positions':sum(j['role'] in ('writer','reader','designer','critic') for j in jobs),
                  'all_positions':len(jobs),'world_unit':24,'smokes':2,'fixture_reduced':fixture},
        'conditions':{'C1':'Individual self-contained message, no external codebook.',
                      'T1':'Fixed human-authored compact full-space protocol, frozen before API.',
                      'T2':'Two independent model-led development lines; three successive proposals each, independent training/validation decoders, independent critic after every proposal. Last iteration v3 is final, not best-outcome selection. All versions retained.',
                      'REF':'Deterministic codec, finite exhaustive mathematical reference only, not a capacity-matched model competitor.'},
        'primary':'H2: T2-v3 minus T1 exact nine-field reconstruction at 32 serialized bytes, paired over 24 held-out worlds; average the two T2 lineages within each world.',
        'hypotheses':{'H1':'T1-C1 at 32 bytes','H2':'T2v3-T1 (primary) and T2v3-C1 at 32 bytes',
                      'H3':'T2v3 correct protocol minus missing protocol, same fresh-instance messages, all 24 worlds at 32 bytes',
                      'H4':'T2v3-T2v1 at 32 bytes on independent held-out worlds, v2 trajectory descriptive',
                      'H5':'Full communication cost per correct rule, physical and logical accounting and amortization.'},
        'analysis':{'unit':'world, n=24; lineages averaged within world, not 984 independent replicates',
                    'tests':['T1-C1','T2v3-T1','T2v3-C1','T2v3-missing','T2v3-T2v1'],
                    'multiplicity':'Holm familywise alpha .05 for five exact two-sided paired world sign-flip tests; integer DP after scaling by 2.',
                    'positive_evidence':'Estimate >= .10 and Holm-adjusted p < .05. No equivalence claim from nonsignificance.',
                    'interval':'10000 paired world bootstrap samples stratified by family (8 each), seed 2026101908; empirical indices 249/9749, descriptive not additional decision gate.',
                    'denominator':'All assigned test positions, including failed, unavailable protocol, unsaved writer and dependent skips; those score zero, never replaced.',
                    'secondary':'24/48 byte cells, numeric versus field errors, v2, campaigns, fault controls and cross-model results descriptive; not additional uncorrected superiority tests.',
                    'cost_decision':'H5 positive full-cost efficiency only if primary H2 passes and at N=1000 T2, charged for BOTH campaigns with a fixed equal mixture, has lower bytes/correct than both C1 and T1 in actual API-body, API-plus-reserialized-MCP and logically cached accounting. Mean single-line scenario additionally descriptive. Report all N=1,10,100,1000 and analytic break-even; no dollar claims without prices.'},
        'controls':{'missing':'All 24 worlds, two lineages, final-v3/32; no shared definition; message unchanged.',
                    'subset':'First two preregistered test worlds per family, six worlds, both lineages.',
                    'stale':'Actual v1 definition with v3 message. Unchanged/compatible versions reported, not relabeled incompatible.',
                    'incompatible':'Registered semantic overlay negates a after normal decoding. A controlled incompatibility intervention, not a naturally evolved version. Accuracy remains against original rule, wrong-target following/abstention reported.',
                    'crash':'Extra model writer killed after durable MCP checkpoint but before save acknowledgement/final; only observed exit137 allows recovery reader. No restart.',
                    'corrupt':'Replace middle Unicode character of delivered memory by ? (or ! if already ?), leaving immutable original DB unchanged. Exact intervention independently reconstructed; all serialized bytes counted.',
                    'ambiguous':'Registered overlay permits original decoding and a-negated decoding equally. Expected answers retain common fields/values and null all conflicts. No truth values disclosed.',
                    'cross_model':'gpt-6-luna reader, six worlds, two lineages, final v3/32; independent secondary smoke and separate analysis. No model substitution.'},
        'fairness':'Same per-application model, byte ceilings, output/time/tool quotas for C1/T1/T2. T2 additionally spends model development; NOT matched total development resources. Report that extra cost, do not infer efficiency from H2 alone. Fixed protocol human design labor is unmeasured, not zero.',
        'sealing':'All new disjoint worlds generated before API, private random seed and full oracle outside Git. Hash frozen. E003-E006 source rules excluded. Only training and released per-version validation feedback enter development. Test prompts first created after exclusive immutable lock file records all versions. Workers never mount oracle or research modules.',
        'information':'Only exact serialized {memory:string} result is budgeted; protocol retrieval is a separate explicitly charged channel. No writer final/history/source rule transfers. Narrow reader tool cannot obtain development records. Version IDs/SHA/encoding/media_type count as protocol metadata.',
        'costs':'Payload bytes; full serialized message; raw and serialized protocol and metadata; all negotiation records including failed attempts; API JSON application-layer request/response bytes (not TLS wire bytes); tokens/time; MCP raw log bytes separately. Logical cached scenario counts unique shared objects once plus messages; actual physical scenario counts repeated protocol/history traffic. N=1/10/100/1000, no free dictionary.',
        'models':{'primary':'gpt-6-sol','secondary':'gpt-6-luna'},'provider':'https://185.170.154.169/v1',
        'provenance':'Gateway-declared model identity, not independently attested weights/seeds. No explicit model sampling seed.',
        'limits':{'concurrency':1,'designer_seconds':600,'critic_seconds':600,'writer_seconds':300,'reader_seconds':180,
                  'request_seconds':120,'development_output_tokens':8192,'application_output_tokens':4096,
                  'responses_per_context':6,'save_attempts':2,'series_seconds':86400,'worker_retries':0,'spend_usd':None,'request_budget':None},
        'recovery':'Terminal contexts never retried. Resume only first pending position, refuse running/orphan workers or pending provider attempts. Transient 429/502/503/504/timeout/connection: catalog checks at30/120/300 seconds then continue only next position. Auth/TLS/nontransient/provider identity mismatch, changed inputs/code, leakage or STOP abort. Secondary absent/incompatible smoke marks only secondary unavailable; auth/TLS errors abort. No outcome-based replacements.',
        'authorization':'User authorizes this full E007 specification and API without monetary limits; local commits only; no push or new infrastructure.',
        'bounds':bounds(),'fixed_protocol_sha256':hashlib.sha256(FIXED_SPEC.encode()).hexdigest(),
        'limitations':['Synthetic nine-field rules are not open-ended knowledge, causality or consciousness.',
                       'Two development campaigns limit claims about protocol emergence variability.',
                       'A compact model proposal may rediscover a familiar code; performance does not prove novelty.',
                       'Machine-native representations allowed but model decoder ability remains a limit.',
                       'Known-correct source rules; not rule discovery from observations.'],
        'schedule':jobs}


def prepare(identity, gate=None, fixture=False):
    if not re.fullmatch(r'e007-[a-z0-9-]{1,24}',identity):
        raise ValueError('invalid study identity')
    if not fixture:
        gate=Path(gate).resolve(strict=True)
        verified=json.loads(gate.read_text())
        if not verified['pass'] or not verified['fixture_pass'] or verified['implementation_hashes']!=implementation_hashes():
            raise ValueError('fresh complete offline gate required')
    study=ROOT/'runs'/identity
    study.mkdir(exist_ok=False)
    excluded,prior_hashes=set(),{}
    for path in sorted((ROOT/'runs').glob('e00[3-6]-*/oracle.json')):
        prior=json.loads(path.read_text())
        for w in prior.get('worlds',[]):
            if 'rule' in w:
                excluded.add(json.dumps(w['rule'],sort_keys=True))
        prior_hashes[str(path)]=digest(path)
    inputs=corpus(2026101907 if fixture else secrets.randbits(128),excluded)
    jobs=schedule(inputs)
    if fixture:
        jobs=[j for j in jobs if j['world']=='none' or (j['phase']=='development' and j['world'] in {'training-01','training-02','validation-01','validation-02','validation-03'})
              or (j['phase']!='development' and j['world']=='test-01' and j['budget']==32)]
    write_json(study/'oracle.json',inputs)
    reg=preregistration(inputs,jobs,fixture)
    reg.update(image=image_id('python:3.11-slim-bookworm'),runtime=runtime_identity(),implementation_hashes=implementation_hashes(),
               oracle_sha256=digest(study/'oracle.json'),excluded_oracle_hashes=prior_hashes,
               gate_path=str(gate) if gate else None,gate_sha256=digest(gate) if gate else None)
    write_json(study/'registration.json',reg)
    write_json(study/'manifest.json',{'registration_sha256':digest(study/'registration.json')})
    probe=study/'isolation-worker'
    create_worker(probe,'A','none')
    if not isolation_probe(reg['image'],probe,study/'isolation.json')['isolation_pass']:
        raise ValueError('isolation gate failed')
    for campaign in ('p1','p2'):
        archive_write(study/'archives'/campaign/'seed',lambda b:b.put('training',{'scope':'training-only; not verified protocol claims','worlds':inputs['splits']['training']}))
    def fixed(b):
        sha=b.put_blob(FIXED_SPEC.encode(),'text/plain')
        b.put('protocol:fixed-v1',{'version':'fixed-v1','blob_sha256':sha,'encoding':'utf8','media_type':'text/plain',
                                  'author':'pre-API-human-fixed','claim_status':'exhaustively_verified_by_independent_finite_codec_gate',
                                  'reason':'full-space compact reference protocol; not emergent','compatibility':'fixed-v1 only','accepted':[],'rejected':[]})
    archive_write(study/'archives'/'T1'/'seed',fixed)
    write_json(study/'heads.json',{c:str(study/'archives'/c/'seed') for c in ('p1','p2','T1')})
    write_json(study/'head-hashes.json',{c:digest(study/'archives'/c/'seed'/'state/continuum.sqlite3') for c in ('p1','p2','T1')})
    Jobs(study/'jobs.sqlite3',jobs)
    if not fixture:
        write_json(PROJECT/'docs/research/E007-PREREGISTRATION.json',reg)
        append_journal(study,'registered')
    return study


def load(study):
    study=Path(study).resolve(strict=True)
    if study.parent!=(ROOT/'runs').resolve():
        raise ValueError('study outside authorized research contour')
    reg=json.loads((study/'registration.json').read_text())
    manifest=json.loads((study/'manifest.json').read_text())
    if (reg['implementation_hashes']!=implementation_hashes() or reg['runtime']!=runtime_identity()
        or manifest['registration_sha256']!=digest(study/'registration.json') or reg['oracle_sha256']!=digest(study/'oracle.json')
        or (reg['gate_path'] and reg['gate_sha256']!=digest(reg['gate_path']))):
        raise ValueError('registered source/runtime/inputs/gate changed')
    return reg


def append_journal(study,status,outcome=None):
    path=PROJECT/'docs/research/journal.jsonl'
    prior=[r for r in map(json.loads,path.read_text(encoding='utf-8').splitlines()) if r['entity_id']=='E-007']
    reg=json.loads((study/'registration.json').read_text())
    row={'event_id':f'E-007/{len(prior)+1}','entity_id':'E-007','kind':'experiment','at_utc':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
         'status':status,'evidence_tier':'proposal' if outcome is None else 'observed_model',
         'summary':'Model-developed shared protocols: creation, transfer, failure controls and full communication cost.',
         'details':{'design':reg['design'],'inputs':str(study/'oracle.json'),'evaluation':reg['primary'],
                    'conditions':reg['sample'],'outcome':outcome,'limitations':reg['limitations']},
         'refs':['E-005','E-006',str(study/'registration.json')],
         'provenance':{'actor':'engineering-e007-20261019','model_actual':'host-model-not-exposed' if outcome is None else reg['models'],
                       'source_snapshot':str(study/'manifest.json')},'supersedes':prior[-1]['event_id'] if prior else None}
    with path.open('a',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps(row,ensure_ascii=False)+'\n')


def copy_source(study,run,source,source_id):
    origin=source/'state/continuum.sqlite3'
    copy_database(origin,run/'state/continuum.sqlite3')
    write_json(run/'source.json',{'source_id':source_id,'source':str(source),'db_sha256':digest(origin),
                                 'copy_sha256':digest(run/'state/continuum.sqlite3'),'history_copied':False})


def run_position(study,reg,job,provider):
    run=study/'units'/job['id']
    if run.exists():
        raise RuntimeError('position already materialized; inspect orphan, never relaunch')
    make_unit(run)
    heads=json.loads((study/'heads.json').read_text())
    head_hashes=json.loads((study/'head-hashes.json').read_text())
    if any(digest(Path(path)/'state/continuum.sqlite3')!=head_hashes[c] for c,path in heads.items()):
        raise PermissionError('immutable campaign head changed')
    role=job['role']
    world=None
    if job['world']!='none':
        if job['split']=='test' and not (study/'protocol-lock.json').exists():
            raise PermissionError('test still sealed')
        if job['split']=='test':
            lock=json.loads((study/'protocol-lock.json').read_text())
            lock_job=next(j for j in reg['schedule'] if j['role']=='lock')
            lock_result=json.loads((study/'units'/lock_job['id']/'result.json').read_text())
            if lock_result['protocol_lock_sha256']!=digest(study/'protocol-lock.json') or lock['heads']!=heads or lock['head_hashes']!=head_hashes:
                raise PermissionError('frozen protocol lock changed')
        oracle=json.loads((study/'oracle.json').read_text())
        world=next(w for w in oracle['splits'][job['split']] if w['id']==job['world'])
    if role=='lock':
        versions={}
        for campaign in ('p1','p2'):
            db,index,objects=snapshot(Path(heads[campaign])/'state/continuum.sqlite3')
            for v in (1,2,3):
                key=f'protocol:{campaign}-v{v}'
                versions[key]=json.loads(objects[index[key]]['content']) if key in index else None
        with (study/'protocol-lock.json').open('x',encoding='utf-8') as f:
            json.dump({'at':time.time(),'heads':heads,'head_hashes':head_hashes,'versions':versions,'registration_sha256':digest(study/'registration.json')},f,indent=2)
        return {'status':'completed','job':job,'protocol_lock_sha256':digest(study/'protocol-lock.json')}
    if role=='reader':
        source=study/'units'/job['source']
        prior=json.loads((source/'result.json').read_text())
        accepted=('injected_crash_after_commit',) if job.get('control')=='crash' else ('completed',)
        if prior['status'] not in accepted or not prior.get('saved'):
            return {'status':'skipped_dependency','job':job,'reason':'predecessor did not reach its registered successful terminal state'}
        if job.get('control')=='cross_model' and provider is None:
            return {'status':'secondary_unavailable','job':job}
        copy_source(study,run,source,job['source'])
    elif job.get('campaign') in heads:
        source=Path(heads[job['campaign']])
        copy_source(study,run,source,source.name)
    if role=='feedback':
        cases=[]
        for prior in reg['schedule']:
            if prior['role']=='reader' and prior['phase']=='development' and prior['protocol_version']==job['protocol_version']:
                result=json.loads((study/'units'/prior['id']/'result.json').read_text())
                verified=json.loads((study/'units'/prior['id']/'audit.json').read_text()) if (study/'units'/prior['id']/'audit.json').exists() else {'pass':False}
                target=next(w for w in json.loads((study/'oracle.json').read_text())['splits'][prior['split']] if w['id']==prior['world'])
                writer_audit_path=study/'units'/prior['source']/'audit.json'
                writer_audit=json.loads(writer_audit_path.read_text()) if writer_audit_path.exists() else {}
                cases.append({'world':target,'reader_id':prior['id'],'status':result['status'],'lineage_verified':verified['pass'],
                              'memory':writer_audit.get('memory'),'evaluation':score(result.get('answer'),target),
                              'result_sha256':digest(study/'units'/prior['id']/'result.json')})
        feedback={'claim_status':'externally_computed_arithmetic_and_lineage','protocol_version':job['protocol_version'],'cases':cases,
                  'scope':'Training/validation cases only. Successful lineage required; not exhaustive protocol proof. Test remains sealed.'}
        archive_write(run,lambda b:b.put('feedback:'+job['protocol_version'],feedback))
        heads[job['campaign']]=str(run)
        head_hashes[job['campaign']]=digest(run/'state/continuum.sqlite3')
        write_json(study/'heads.json',heads)
        write_json(study/'head-hashes.json',head_hashes)
        return {'status':'completed','job':job,'cases':len(cases)}
    if role in ('writer','reader') and job.get('protocol_version') and job['condition']!='C1':
        _,index,_=snapshot(run/'state/continuum.sqlite3')
        if 'protocol:'+job['protocol_version'] not in index:
            return {'status':'skipped_protocol_unavailable','job':job}
    result=execute(study,reg,job,world,provider)
    verified=audit(study,job,'scripted-fixture' if reg['fixture'] else provider.model)
    write_json(run/'audit.json',verified)
    if verified.get('executed_successfully') is True and not verified['pass']:
        raise PermissionError('independent lineage audit failed: '+verified['reason'])
    if role in ('designer','critic') and result['status']=='completed':
        if not verified['pass']:
            raise PermissionError('unverified publication cannot become shared state')
        heads[job['campaign']]=str(run)
        head_hashes[job['campaign']]=digest(run/'state/continuum.sqlite3')
        write_json(study/'heads.json',heads)
        write_json(study/'head-hashes.json',head_hashes)
    return result


def run(study,authorize=False,fixture_provider=None):
    study=Path(study).resolve()
    reg=load(study)
    if reg['fixture']!=bool(fixture_provider):
        raise PermissionError('fixture/live mismatch')
    if not reg['fixture'] and not authorize:
        raise PermissionError('explicit API authorization required')
    ledger=Jobs(study/'jobs.sqlite3')
    state=ledger.state()
    if any(v['status']=='running' for v in state.values()):
        raise RuntimeError('running/orphan context exists; inspect actual process before resolution')
    providers={}
    if fixture_provider:
        providers={'primary':fixture_provider,'secondary':fixture_provider}
    else:
        spend=SpendLedger(study/'provider-ledger.sqlite3',unbounded=True)
        providers={k:MeasuredProvider(reg['provider'],model,spend,study/'provider.jsonl',authorize=True) for k,model in reg['models'].items()}
    if not (study/'network-start.json').exists():
        with (study/'network-start.json').open('x') as f:
            json.dump({'at':time.time(),'fixture':reg['fixture']},f)
    start=json.loads((study/'network-start.json').read_text())['at']
    if not fixture_provider:
        for key,provider in list(providers.items()):
            directory=study/('smoke-'+key)
            directory.mkdir(exist_ok=True)
            if (directory/'unavailable.json').exists():
                providers[key]=None
                continue
            if (directory/'smoke.json').exists():
                continue
            if (directory/'smoke-started').exists():
                raise RuntimeError('incomplete smoke; never retry')
            try:
                if provider.model not in provider.models():
                    if key=='primary':
                        recover(provider,study)
                    else:
                        raise ValueError('secondary model absent from catalog')
                smoke(directory,provider)
            except Exception as exc:
                # Secondary compatibility may be unavailable; credentials/TLS/HTTP safeguard errors still abort.
                if key=='primary' or not isinstance(exc,ValueError):
                    raise
                write_json(directory/'unavailable.json',{'reason':str(exc),'type':type(exc).__name__,'at':time.time()})
                providers[key]=None
    for job in reg['schedule']:
        if state[job_id(job)]['status']!='pending':
            continue
        load(study)
        if (study/'STOP').exists() or time.time()-start>=reg['limits']['series_seconds']:
            raise RuntimeError('registered STOP/deadline')
        ledger.claim(job_id(job))
        print(json.dumps({'event':'job_started','job':job['id'],'role':job['role']}),flush=True)
        provider=providers['secondary' if job.get('control')=='cross_model' else 'primary']
        try:
            result=run_position(study,reg,job,provider)
        except Exception as exc:
            result={'status':'failed_controller','job':job,'failure_type':type(exc).__name__,'failure':str(exc)}
        write_json(study/'units'/job['id']/'result.json',result)
        ledger.finish(job_id(job),result)
        print(json.dumps({'event':'job_result','job':job['id'],'status':result['status'],'failure':result.get('failure')}),flush=True)
        if result['status']=='failed_controller' or result.get('failure_type')=='PermissionError':
            raise RuntimeError('controller/safeguard failure; stop without replacement')
        if transient(result):
            recover(provider,study)
        elif result.get('failure_origin')=='provider':
            raise RuntimeError('nontransient provider failure; stop without replacement')
    return {'status':'completed','positions':len(ledger.state())}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run'))
    parser.add_argument('--study-id')
    parser.add_argument('--study',type=Path)
    parser.add_argument('--gate',type=Path)
    parser.add_argument('--authorize-api',action='store_true')
    args=parser.parse_args()
    print(prepare(args.study_id,args.gate) if args.action=='prepare' else run(args.study,args.authorize_api))
