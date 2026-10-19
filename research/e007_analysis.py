"""World-level inference and explicitly scoped communication accounting for E007."""
from collections import Counter
import json
import math
from pathlib import Path
import random
from .common import digest, write_json
from .e003 import Jobs, job_id
from .e007_audit import audit, rows, score, snapshot


def exact_sign_flip(differences):
    scaled=[round(2*d) for d in differences]
    if any(abs(2*d-s)>1e-12 for d,s in zip(differences,scaled)):
        raise ValueError('world differences not in half-integer lattice')
    counts={0:1}
    for value in scaled:
        new=Counter()
        for total,multiplicity in counts.items():
            new[total+value]+=multiplicity
            new[total-value]+=multiplicity
        counts=dict(new)
    observed=abs(sum(scaled))
    return sum(n for total,n in counts.items() if abs(total)>=observed)/(2**len(scaled))


def holm(values):
    adjusted={}
    running=0
    for i,(name,p) in enumerate(sorted(values.items(),key=lambda x:x[1])):
        running=max(running,min(1,p*(len(values)-i)))
        adjusted[name]=running
    return adjusted


def statistics(worlds,scores):
    comparisons=[('T1-C1','T1','C1'),('T2v3-T1','T2v3','T1'),('T2v3-C1','T2v3','C1'),
                 ('T2v3-missing','T2v3','missing'),('T2v3-T2v1','T2v3','T2v1')]
    groups=[[w['id'] for w in worlds if w['family']==family] for family in sorted({w['family'] for w in worlds})]
    result={}
    for name,left,right in comparisons:
        differences={w['id']:scores[w['id']][left]-scores[w['id']][right] for w in worlds}
        rng=random.Random(2026101908)
        samples=sorted(sum(differences[rng.choice(g)] for g in groups for _ in g)/len(worlds) for _ in range(10000))
        result[name]={'estimate':sum(differences.values())/len(worlds),'bootstrap_95':[samples[249],samples[9749]],
                      'exact_two_sided_p':exact_sign_flip(list(differences.values())),'n_worlds':len(worlds)}
    adjusted=holm({k:v['exact_two_sided_p'] for k,v in result.items()})
    for k,value in result.items():
        value['holm_p']=adjusted[k]
        value['positive_rule_met']=value['estimate']>=.1 and adjusted[k]<.05
    return result


def break_even(candidate,control):
    # (Dc+N*mc)/(N*pc) < (Db+N*mb)/(N*pb).
    pc,pb=candidate['probability'],control['probability']
    if pc==0:
        return {'first_positive_integer_N':None,'reason':'candidate has no observed successes'}
    if pb==0:
        return {'first_positive_integer_N':1,'reason':'control has no observed successes; candidate cost/correct finite'}
    slope=pc*control['per_use_bytes']-pb*candidate['per_use_bytes']
    intercept=pb*candidate['setup_bytes']-pc*control['setup_bytes']
    if slope>0:
        return {'first_positive_integer_N':max(1,math.floor(intercept/slope)+1),'reason':'strict cost/correct crossing','slope':slope,'intercept':intercept}
    if slope==0:
        return {'first_positive_integer_N':1 if intercept<0 else None,'reason':'equal marginal efficiency'}
    return {'first_positive_integer_N':1 if slope>intercept else None,
            'reason':'no eventual amortization advantage; possible bounded small-N advantage only',
            'last_advantage_N_exclusive':intercept/slope,'slope':slope,'intercept':intercept}


def mcp_bytes(path):
    if not path.exists():
        return 0
    return sum(len(json.dumps(e['message']).encode())+1 for e in rows(path)
               if (e.get('channel')=='mcp' or e.get('event')=='mcp_response') and 'message' in e)


def costs(study,reg,evaluated,network):
    measured={j['id']:{'api_body_bytes':0,'api_complete':True,'mcp_reencoded_bytes':0,'raw_log_bytes':0,
                       'input_tokens':0,'output_tokens':0,'message_attempt_bytes':0} for j in reg['schedule']}
    for event in network:
        worker=event.get('worker')
        if worker not in measured:
            continue
        item=measured[worker]
        if event['event']=='transport_bytes':
            item['api_body_bytes']+=event['request_body_bytes']+event['response_body_bytes']
            item['api_complete'] &= event['request_sent'] and event['response_complete']
        elif event['event']=='response':
            usage=event['response'].get('usage',{})
            for key in ('input_tokens','output_tokens'):
                item[key]+=usage.get(key,0)
    for worker,item in measured.items():
        requests=[e for e in network if e.get('worker')==worker and e['event']=='request_started']
        transports=[e for e in network if e.get('worker')==worker and e['event']=='transport_bytes']
        item['api_complete'] &= len(requests)==len(transports)
        if len(requests)==len(transports):
            item['api_complete'] &= all(len(json.dumps(req['payload'],ensure_ascii=False).encode())==wire['request_body_bytes'] for req,wire in zip(requests,transports))
    for job in reg['schedule']:
        unit=study/'units'/job['id']
        item=measured[job['id']]
        for name in ('session.jsonl','archive.jsonl'):
            path=unit/'supervisor'/name
            item['mcp_reencoded_bytes']+=mcp_bytes(path)
            if path.exists():
                item['raw_log_bytes']+=path.stat().st_size
                if job['role']=='writer':
                    for e in rows(path):
                        if e.get('event')=='tool_result' and e['name']=='save_memory':
                            item['message_attempt_bytes']+=len(json.dumps({'memory':e['arguments']['memory']}).encode())
    heads=json.loads((study/'heads.json').read_text())
    setup={}
    for campaign in ('p1','p2','T1'):
        db,index,objects=snapshot(Path(heads[campaign])/'state/continuum.sqlite3')
        content=sum(len(o['content']) for o in objects.values())
        metadata=sum(len(json.dumps({k:v for k,v in o.items() if k!='content'},ensure_ascii=False).encode()) for o in objects.values())
        index_bytes=sum(len(t['result'].encode()) for t in db['tasks'])
        dev=[measured[j['id']] for j in reg['schedule'] if j['phase']=='development' and j.get('campaign')==campaign]
        seed_mcp=mcp_bytes(study/'archives'/campaign/'seed'/'supervisor/archive.jsonl')
        setup[campaign]={'unique_content_bytes':content,'object_metadata_bytes':metadata,'current_index_bytes':index_bytes,
                         'logical_bytes':content+metadata+index_bytes,'api_body_bytes':sum(x['api_body_bytes'] for x in dev),
                         'mcp_reencoded_bytes':seed_mcp+sum(x['mcp_reencoded_bytes'] for x in dev),
                         'input_tokens':sum(x['input_tokens'] for x in dev),'output_tokens':sum(x['output_tokens'] for x in dev),
                         'protocol_versions':len([k for k in index if k.startswith('protocol:')]),'unique_objects':len(objects)}
    setup['C1']={k:0 for k in setup['T1']}
    modes=('physical_api_body','physical_api_plus_mcp_reencoded','logical_shared_state')
    scenarios={mode:{} for mode in modes}
    for campaign in ('C1','T1','p1','p2'):
        chosen=[r for r in evaluated if r['job']['phase']=='test' and r['job']['role']=='reader' and r['job']['budget']==32
                and r['job']['campaign']==campaign and (campaign in ('C1','T1') or r['job']['protocol_version'].endswith('v3'))]
        denominator=len(chosen)
        probability=sum(r['score']['rule_correct'] for r in chosen)/denominator if denominator else 0
        pairs=[(measured[r['job']['source']],measured[r['job']['id']]) for r in chosen]
        api=sum(a['api_body_bytes']+b['api_body_bytes'] for a,b in pairs)/denominator if denominator else 0
        mcp=sum(a['mcp_reencoded_bytes']+b['mcp_reencoded_bytes'] for a,b in pairs)/denominator if denominator else 0
        messages=sum(a['message_attempt_bytes'] for a,b in pairs)/denominator if denominator else 0
        for mode in modes:
            initial=setup[campaign]['logical_bytes'] if mode=='logical_shared_state' else setup[campaign]['api_body_bytes']
            per_use=messages if mode=='logical_shared_state' else api
            if mode=='physical_api_plus_mcp_reencoded':
                initial+=setup[campaign]['mcp_reencoded_bytes']
                per_use+=mcp
            value={'setup_bytes':initial,'per_use_bytes':per_use,'probability':probability,'denominator_worlds':denominator}
            value['amortization']={str(n):{'total_bytes':initial+n*per_use,'expected_correct':n*probability,
                'bytes_per_correct':(initial+n*per_use)/(n*probability) if probability else None} for n in (1,10,100,1000)}
            scenarios[mode][campaign]=value
        # Both lines were run, not selected. Pooled mean assumes a random line; total realized development stays visible below.
    for mode in modes:
        left,right=scenarios[mode]['p1'],scenarios[mode]['p2']
        pooled={key:(left[key]+right[key])/2 for key in ('setup_bytes','per_use_bytes','probability')}
        pooled['interpretation']='Mean cost/outcome for a randomly selected independent development line; not best-line selection. Real experiment paid for both lines.'
        pooled['amortization']={str(n):{'total_bytes':pooled['setup_bytes']+n*pooled['per_use_bytes'],'expected_correct':n*pooled['probability'],
            'bytes_per_correct':(pooled['setup_bytes']+n*pooled['per_use_bytes'])/(n*pooled['probability']) if pooled['probability'] else None} for n in (1,10,100,1000)}
        scenarios[mode]['T2_mean_line']=pooled
        # Conservative scenario: pay for both campaigns, use the predeclared equal mixture, never choose best.
        both=dict(pooled,setup_bytes=left['setup_bytes']+right['setup_bytes'],interpretation='Both development campaigns paid; equal mixture, no outcome selection.')
        both['amortization']={str(n):{'total_bytes':both['setup_bytes']+n*both['per_use_bytes'],'expected_correct':n*both['probability'],
            'bytes_per_correct':(both['setup_bytes']+n*both['per_use_bytes'])/(n*both['probability']) if both['probability'] else None} for n in (1,10,100,1000)}
        scenarios[mode]['T2_both_lines']=both
        for name in ('p1','p2','T2_mean_line','T2_both_lines'):
            scenarios[mode][name]['break_even']={control:break_even(scenarios[mode][name],scenarios[mode][control]) for control in ('C1','T1')}
    return {'measurement_scope':'API: actual HTTP bodies, excluding headers/TLS. MCP: reserialized observed messages, not exact wire framing. Logical: unique shared content+object metadata+current index, plus all proposed memory messages including rejected attempts; optimistic cached-state scenario, not actual network caching. Human design labor and monetary price unknown.',
            'api_measurements_available':not reg['fixture'],'api_measurements_complete':not reg['fixture'] and all(x['api_complete'] for x in measured.values()),
            'development_setup':setup,'per_position':measured,'scenarios':scenarios,
            'actual_totals':{'api_body_bytes':sum(e['request_body_bytes']+e['response_body_bytes'] for e in network if e['event']=='transport_bytes'),
                'mcp_reencoded_bytes':sum(x['mcp_reencoded_bytes'] for x in measured.values())+sum(mcp_bytes(study/'archives'/c/'seed'/'supervisor/archive.jsonl') for c in ('p1','p2','T1')),
                'raw_worker_logs_bytes':sum(x['raw_log_bytes'] for x in measured.values()),
                'input_tokens':sum(e['response'].get('usage',{}).get('input_tokens',0) for e in network if e['event']=='response'),
                'output_tokens':sum(e['response'].get('usage',{}).get('output_tokens',0) for e in network if e['event']=='response')}}


def evaluate(study):
    from .e007 import load
    study=Path(study).resolve()
    reg=load(study)
    oracle=json.loads((study/'oracle.json').read_text())
    if digest(study/'oracle.json')!=reg['oracle_sha256']:
        raise ValueError('oracle changed')
    states=Jobs(study/'jobs.sqlite3').state()
    if set(states)!={job_id(j) for j in reg['schedule']} or any(v['status'] in ('pending','running') for v in states.values()):
        raise ValueError('registered series not terminal')
    lock=json.loads((study/'protocol-lock.json').read_text())
    lock_job=next(j for j in reg['schedule'] if j['role']=='lock')
    if states[job_id(lock_job)]['report']['protocol_lock_sha256']!=digest(study/'protocol-lock.json'):
        raise ValueError('lock not bound to completed position')
    if any(digest(Path(path)/'state/continuum.sqlite3')!=lock['head_hashes'][c] for c,path in lock['heads'].items()):
        raise ValueError('frozen protocol source changed')
    network=rows(study/'provider.jsonl')
    worlds={w['id']:w for split in oracle['splits'].values() for w in split}
    evaluated=[]
    for job in reg['schedule']:
        result=json.loads((study/'units'/job['id']/'result.json').read_text())
        if result!=states[job_id(job)]['report']:
            raise ValueError('ledger/result mismatch')
        if job['role'] not in ('writer','reader','designer','critic'):
            continue
        model='scripted-fixture' if reg['fixture'] else reg['models']['secondary' if job.get('control')=='cross_model' else 'primary']
        checked=audit(study,job,model,network)
        if job.get('split')=='test' and (study/'units'/job['id']/'supervisor/session.jsonl').exists():
            starts=[e['at'] for e in rows(study/'units'/job['id']/'supervisor/session.jsonl') if e.get('event')=='command_execution']
            if len(starts)!=1 or starts[0]<lock['at']:
                raise ValueError('test execution preceded protocol lock')
        if checked.get('executed_successfully') is True and not checked['pass']:
            raise ValueError('integrity failure in '+job['id']+': '+checked['reason'])
        value=score(result.get('answer') if checked['pass'] else None,worlds[job['world']],job.get('control')) if job['role']=='reader' else None
        evaluated.append({'job':job,'status':result['status'],'audit':checked,'score':value})
    test_worlds=[w for w in oracle['splits']['test'] if any(j['world']==w['id'] and j['phase']=='test' for j in reg['schedule'])]
    scores={w['id']:{k:0 for k in ('C1','T1','T2v1','T2v2','T2v3','missing')} for w in test_worlds}
    groups={}
    for row in evaluated:
        job=row['job']
        if job['role']!='reader' or job.get('split')!='test':
            continue
        label=job.get('control') or (job['protocol_version'] if job['condition']=='T2' else job['condition'])
        key=f'{label}/{job["budget"]}'
        g=groups.setdefault(key,{'denominator':0,'lineage_verified':0,'rule_correct':0,'numeric_correct':0,'all_correct':0,'control_expected_correct':0,
                                'correct_fields':0,'wrong_fields':0,'null_fields':0,'arithmetic_error_with_correct_rule':0})
        g['denominator']+=1
        g['lineage_verified']+=row['audit']['pass']
        for k in row['score']:
            if k in g:
                g[k]+=row['score'][k]
        if job['budget']==32 and (job['phase']=='test' or job.get('control')=='missing'):
            if job.get('control')=='missing':
                score_key,weight='missing',.5
            elif job['condition']=='T2':
                score_key,weight='T2'+job['protocol_version'].split('-')[1],.5
            else:
                score_key,weight=job['condition'],1
            scores[job['world']][score_key]+=weight*int(row['score']['rule_correct'])
    stats=statistics(test_worlds,scores)
    communication=costs(study,reg,evaluated,network)
    cheaper=[]
    for mode,values in communication['scenarios'].items():
        candidate=values['T2_both_lines']['amortization']['1000']['bytes_per_correct']
        cheaper.append(candidate is not None and all(values[c]['amortization']['1000']['bytes_per_correct'] is None or candidate<values[c]['amortization']['1000']['bytes_per_correct'] for c in ('C1','T1')))
    report={'experiment':'E-007','fixture':reg['fixture'],'terminal':True,'status_counts':dict(Counter(v['status'] for v in states.values())),
            'model_positions':len(evaluated),'independent_test_worlds':len(test_worlds),'lineage_verified_contexts':sum(r['audit']['pass'] for r in evaluated),
            'primary':stats['T2v3-T1'],'contrasts':stats,'groups':groups,'world_scores':scores,'costs':communication,
            'H5_positive_rule_met':bool(stats['T2v3-T1']['positive_rule_met'] and all(cheaper) and communication['api_measurements_complete']),
            'api_attempts':sum(e['event']=='request_started' for e in network),'returned_responses':sum(e['event']=='response' for e in network),
            'registration_sha256':digest(study/'registration.json'),'protocol_lock_sha256':digest(study/'protocol-lock.json'),'rows':evaluated}
    write_json(study/'report.json',report)
    return report


if __name__=='__main__':
    import sys
    report=evaluate(Path(sys.argv[1]))
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','world_scores','costs')},ensure_ascii=False))
