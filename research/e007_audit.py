"""Independent evidence reconstruction and arithmetic; never executes protocol bodies."""
import base64
import hashlib
import json
from .common import digest, source_hashes
from .e003_audit import pairs, read_db
from .e004_audit import calculate, same


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def network_chain(run, result, events, network, model):
    from .e007_protocol import TOOLS
    messages = [e['message'] for e in events if e.get('event')=='worker_message']
    histories = [e['history'] for e in messages if e['channel']=='responses']
    job = result['job']
    text = json.loads((run/'workers'/job['stage']/'repo/PROMPT.txt').read_text())['prompt']
    if not histories or histories[0] != [{'role':'user','content':text}]:
        raise ValueError('non-fresh initial context')
    requests = [e for e in network if e.get('worker')==job['id'] and e['event']=='request_started']
    responses = [e for e in network if e.get('worker')==job['id'] and e['event']=='response']
    receipts = [e for e in events if e.get('event')=='tool_result']
    actions = [m for m in messages if m['channel']=='tool']
    if len(requests)!=len(histories) or len(responses)!=len(requests) or len(receipts)!=len(actions):
        raise ValueError('network/action counts differ')
    reconstructed, used, final = histories[0], 0, None
    crash = result['status']=='injected_crash_after_commit'
    for i,(req,res) in enumerate(zip(requests,responses)):
        if req['attempt']!=res['attempt'] or req['payload']['input']!=histories[i] or histories[i]!=reconstructed:
            raise ValueError('unbound request/history')
        if req['payload']['tools']!=TOOLS[job['role']] or req['payload']['model']!=model or req['payload']['store'] is not False or req['payload']['parallel_tool_calls'] is not False:
            raise ValueError('wrong model/tools/storage')
        value = res['response']
        if value['model']!=model or value['status']!='completed':
            raise ValueError('wrong returned model/status')
        reconstructed = reconstructed+value['output']
        calls = [v for v in value['output'] if v.get('type')=='function_call']
        if calls:
            for call in calls:
                if used>=len(actions):
                    raise ValueError('model call not executed')
                action,receipt = actions[used],receipts[used]
                args = json.loads(call['arguments'])
                if action['name']!=call['name'] or receipt['name']!=call['name'] or not same(action['arguments'],args) or not same(receipt['arguments'],args):
                    raise ValueError('tool content not authored by returned model')
                used += 1
                if crash and used==len(receipts):
                    if call['name']!='save_memory' or not receipt['value']['saved'] or i!=len(requests)-1:
                        raise ValueError('invalid interrupted receipt')
                else:
                    reconstructed.append({'type':'function_call_output','call_id':call['call_id'],'output':json.dumps(receipt['value'])})
        else:
            text = ''.join(c.get('text','') for v in value['output'] if v.get('type')=='message' for c in v.get('content',[]))
            final = json.loads(text)
            if i!=len(requests)-1:
                raise ValueError('continued after final')
    finals = [json.loads(m['line']) for m in messages if m['channel']=='worker']
    if used!=len(receipts):
        raise ValueError('unused tool receipt')
    if crash:
        injected = [e for e in events if e.get('event')=='injected_crash_after_commit']
        if final is not None or finals or len(injected)!=1 or injected[0]['receipt_delivered'] or injected[0]['kill_result']['exit_status']!=0 or result['exit_status']!=137:
            raise ValueError('crash was not observed before acknowledgement/final')
    elif not same(final,result.get('answer')) or not same(finals,[final]):
        raise ValueError('unbound final output')
    return receipts


def snapshot(path):
    db = read_db(path)
    objects = {o['sha256']:o for o in db['knowledge_objects']}
    for sha,obj in objects.items():
        if hashlib.sha256(obj['content']).hexdigest()!=sha:
            raise ValueError('object digest mismatch')
    if len(db['tasks'])>1:
        raise ValueError('multiple archive tasks')
    index = json.loads(db['tasks'][0]['result']) if db['tasks'] and db['tasks'][0]['result'] else {}
    if not all(sha in objects for sha in index.values()):
        raise ValueError('dangling archive reference')
    return db,index,objects


def expected(world, control=None):
    result = calculate(world['rule'], world['queries'])
    if control=='ambiguous':
        other = calculate(dict(world['rule'], a=-world['rule']['a']),world['queries'])
        result['rule'] = dict(result['rule'],a=None)
        result['predictions'] = [a if a==b else None for a,b in zip(result['predictions'],other['predictions'])]
        for k in ('sum','contrast'):
            if result[k]!=other[k]:
                result[k]=None
    return result


def score(answer, world, control=None):
    truth = calculate(world['rule'],world['queries'])
    want = expected(world,control)
    valid = isinstance(answer,dict) and set(answer)==set(want)
    rule = answer.get('rule') if valid else None
    correct = wrong = null = 0
    for k,v in world['rule'].items():
        actual = rule.get(k) if isinstance(rule,dict) else None
        if actual is None:
            null += 1
        elif same(actual,v):
            correct += 1
        else:
            wrong += 1
    full_rule = valid and same(rule,truth['rule'])
    numeric = valid and all(same(answer[k],truth[k]) for k in ('predictions','sum','contrast'))
    return {'rule_correct':bool(full_rule),'numeric_correct':bool(numeric),'all_correct':bool(valid and same(answer,truth)),
            'control_expected_correct':bool(valid and same(answer,want)), 'correct_fields':correct,'wrong_fields':wrong,'null_fields':null,
            'arithmetic_error_with_correct_rule':bool(full_rule and not numeric),'answer':answer}


def audit(study, job, model, network=None):
    run = study/'units'/job['id']
    result = json.loads((run/'result.json').read_text())
    try:
        if result['status'] not in ('completed','budget_rejected','injected_crash_after_commit'):
            return {'pass':False,'executed_successfully':False,'reason':result['status']}
        if result['job']!=job:
            raise ValueError('result job changed')
        if result['status']!='injected_crash_after_commit' and result['exit_status']!=0:
            raise ValueError('nonzero normal exit')
        if source_hashes(run/'workers'/job['stage'])!=json.loads((run/'context-manifest.json').read_text()):
            raise ValueError('worker inputs changed')
        events = rows(run/'supervisor/session.jsonl')
        receipts = network_chain(run,result,events,network if network is not None else rows(study/'provider.jsonl'),model)
        calls = pairs(events)
        db,index,objects = snapshot(run/'state/continuum.sqlite3')
        def retrieved(sha):
            obj = objects[sha]
            if not any(c['name']=='continuum_get_object' and c['arguments']['sha256']==sha and base64.b64decode(c['value']['content_base64'])==obj['content'] for c in calls):
                raise ValueError('object never actually retrieved through MCP')
            return obj['content']
        def persisted(raw):
            sha = hashlib.sha256(raw).hexdigest()
            if sha not in objects or objects[sha]['content']!=raw:
                raise ValueError('model bytes absent from DB')
            put = next(c for c in calls if c['name']=='continuum_put_object' and base64.b64decode(c['arguments']['content_base64'])==raw and c['value']['sha256']==sha)
            if not any(c['name']=='continuum_checkpoint_task' and c['start']>put['end'] and sha in json.loads(c['value']['result']).values() for c in calls):
                raise ValueError('object not durably indexed after put')
            return sha
        role = job['role']
        names = [r['name'] for r in receipts]
        if role in ('writer','reader'):
            if names.count('read_protocol')!=1:
                raise ValueError('protocol retrieval count')
            protocol = next(r['value']['protocol'] for r in receipts if r['name']=='read_protocol')
            version = job.get('protocol_version')
            control = job.get('control') if role=='reader' else None
            if control=='missing':
                version=None
            elif control=='stale':
                version=job['campaign']+'-v1'
            if version and 'protocol:'+version in index:
                record = json.loads(retrieved(index['protocol:'+version]))
                raw = retrieved(record['blob_sha256'])
                want = {'version':version,'sha256':record['blob_sha256'],'encoding':record['encoding'],'media_type':record['media_type'],
                        'body':raw.decode() if record['encoding']=='utf8' else base64.b64encode(raw).decode()}
                if control in ('incompatible','ambiguous'):
                    from .e007_protocol import INCOMPATIBLE, AMBIGUOUS
                    want['controlled_interpretation']=INCOMPATIBLE if control=='incompatible' else AMBIGUOUS
                if protocol!=want:
                    raise ValueError('delivered protocol differs from assigned MCP bytes')
            elif protocol is not None:
                raise ValueError('fabricated protocol')
            if any(r['name']=='read_development' for r in receipts):
                raise ValueError('development history leaked')
        memory = None
        if role=='writer':
            saves = [r for r in receipts if r['name']=='save_memory']
            if names[0]!='read_protocol' or not 1<=len(saves)<=2 or len(names)!=1+len(saves):
                raise ValueError('writer transitions')
            accepted = []
            for i,r in enumerate(saves):
                text = r['arguments']['memory']
                raw = json.dumps({'memory':text}).encode()
                want = {'saved':True,'bytes':len(raw)} if text and len(raw)<=job['budget'] else {'saved':False,'bytes':len(raw),'budget':job['budget'],'attempts_left':1-i}
                if not same(r['value'],want):
                    raise ValueError('incorrect byte feedback')
                if want['saved']:
                    accepted.append(raw)
            if accepted:
                if len(accepted)!=1 or not saves[-1]['value']['saved'] or index.get('message')!=persisted(accepted[0]):
                    raise ValueError('accepted memory mismatch')
                memory=json.loads(accepted[0])['memory']
            elif 'message' in index or result['status']!='budget_rejected':
                raise ValueError('unsaved writer mismatch')
            if result.get('saved') is not bool(accepted) or result['save_attempts']!=len(saves):
                raise ValueError('saved/attempt count not bound')
            if result['status']!='injected_crash_after_commit' and result.get('answer')!={'status':'saved' if accepted else 'not_saved'}:
                raise ValueError('writer final differs from persistence')
        elif role=='reader':
            if sorted(names)!=['read_memory','read_protocol']:
                raise ValueError('reader tools differ')
            source = json.loads((run/'source.json').read_text())
            origin = study/'units'/job['source']/'state/continuum.sqlite3'
            if source['source_id']!=job['source'] or source['db_sha256']!=digest(origin) or read_db(origin)!=db or source['history_copied']:
                raise ValueError('unfaithful predecessor copy')
            raw = retrieved(index['message'])
            want = json.loads(raw)
            if job.get('control')=='corrupt':
                chars=list(want['memory'])
                i=len(chars)//2
                chars[i]='!' if chars[i]=='?' else '?'
                want={'memory':''.join(chars)}
            actual=next(r['value'] for r in receipts if r['name']=='read_memory')
            if actual!=want or len(json.dumps(actual).encode())>job['budget']:
                raise ValueError('delivered memory bytes/ceiling mismatch')
            memory=actual['memory']
        else:
            publication='publish_protocol' if role=='designer' else 'publish_review'
            if names!=['read_development',publication]:
                raise ValueError('development transitions')
            development=receipts[0]['value']
            allowed={k for k in index if k=='training' or k.startswith(('protocol:','review:','feedback:'))}
            own=('protocol:'+job['publish_version']) if role=='designer' else ('review:'+job['review_version'])
            allowed.discard(own)
            if set(development)!=(allowed|{'definitions'}):
                raise ValueError('development corpus/history mismatch')
            for k in allowed:
                if development[k]!=json.loads(retrieved(index[k])):
                    raise ValueError('development record not retrieved')
            if set(development['definitions'])!={k for k in allowed if k.startswith('protocol:')}:
                raise ValueError('definition set mismatch')
            for k,definition in development['definitions'].items():
                record=development[k]
                raw=retrieved(record['blob_sha256'])
                want={'version':k.split(':',1)[1],'sha256':record['blob_sha256'],'encoding':record['encoding'],'media_type':record['media_type'],
                      'body':raw.decode() if record['encoding']=='utf8' else base64.b64encode(raw).decode()}
                if definition!=want:
                    raise ValueError('development definition not bound')
            record=json.loads(objects[index[own]]['content'])
            persisted(objects[index[own]]['content'])
            args=receipts[1]['arguments']
            if record['author']!=run.name+':'+job['stage']:
                raise ValueError('publication author mismatch')
            if role=='designer':
                raw=args['body'].encode() if args['encoding']=='utf8' else base64.b64decode(args['body'],validate=True)
                if record['blob_sha256']!=hashlib.sha256(raw).hexdigest() or objects[record['blob_sha256']]['content']!=raw:
                    raise ValueError('proposed body differs from model call')
                if not any(c['name']=='continuum_put_object' and base64.b64decode(c['arguments']['content_base64'])==raw for c in calls):
                    raise ValueError('model body not put through MCP')
                if any(record[k]!=v for k,v in args.items() if k!='body') or record['version']!=job['publish_version'] or record['claim_status']!='model_proposed_not_universally_verified':
                    raise ValueError('proposal metadata mismatch')
            elif record['review']!=args['review'] or record['claim_status']!='model_commentary_not_verification':
                raise ValueError('review content mismatch')
        return {'pass':True,'memory':memory,'memory_bytes':len(json.dumps({'memory':memory}).encode()) if memory is not None else 0,
                'payload_utf8_bytes':len(memory.encode()) if memory is not None else 0,'mcp_calls':len(calls),'role':role,
                'protocol_result_bytes':len(json.dumps(next(r['value'] for r in receipts if r['name']=='read_protocol')).encode()) if role in ('writer','reader') else 0}
    except (KeyError,ValueError,TypeError,IndexError,StopIteration) as exc:
        return {'pass':False,'executed_successfully':True,'reason':type(exc).__name__+': '+str(exc)}
