"""Explicitly scripted, no-network integration fixture; never empirical model evidence."""
import argparse
import json
import time
from .common import write_json
from .e007 import prepare, run
from .e007_audit import expected
from .e007_analysis import evaluate
from .e007_codec import FIXED_SPEC, fixed_encode
from .e007_codec_audit import independent_fixed


class FixtureProvider:
    fixture=True
    model='scripted-fixture'

    def __init__(self,study):
        self.study=study
        self.attempt=0
        self.jobs={j['id']:j for j in json.loads((study/'registration.json').read_text())['schedule']}

    def respond(self,worker,history,tools,timeout=30,max_output_tokens=4096):
        self.attempt+=1
        job=self.jobs[worker]
        role=job['role']
        calls=[x for x in history if x.get('type')=='function_call']
        outputs=[json.loads(x['output']) for x in history if x.get('type')=='function_call_output']
        def call(name,args):
            return [{'type':'function_call','name':name,'arguments':json.dumps(args),'call_id':f'fixture-{self.attempt}'}]
        def final(value):
            return [{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(value)}]}]
        if not calls:
            output=call('read_development' if role in ('designer','critic') else 'read_protocol',{})
        elif role=='designer':
            if len(calls)==1:
                output=call('publish_protocol',{'body':FIXED_SPEC+'\nSCRIPTED FIXTURE '+job['publish_version'],
                    'encoding':'utf8','media_type':'text/plain','reason':'Scripted integration, NOT model discovery.',
                    'compatibility':'same fixture mapping','accepted':['known fixed format, fixture only'],'rejected':['not evidence of emergence']})
            else:
                output=final({'status':'saved'})
        elif role=='critic':
            output=call('publish_review',{'review':'Scripted independent critic: preserve negative cases; finite fixture is not universal proof.'}) if len(calls)==1 else final({'status':'saved'})
        elif role=='writer':
            if len(calls)==1 or (len(calls)==2 and not outputs[-1]['saved']):
                rule=json.loads(history[0]['content'].split('Correct rule: ',1)[1])
                memory=json.dumps(rule) if job['condition']=='C1' else fixed_encode(rule)
                output=call('save_memory',{'memory':memory})
            else:
                output=final({'status':'saved' if outputs[-1]['saved'] else 'not_saved'})
        elif len(calls)==1:
            output=call('read_memory',{})
        else:
            text=outputs[-1]['memory']
            points=json.loads(history[0]['content'].split('Queries: ',1)[1])
            try:
                if outputs[0]['protocol'] is None:
                    raise ValueError('no fixture codebook')
                rule=independent_fixed(text)
                if job.get('control')=='incompatible':
                    rule['a']=-rule['a']
                answer=expected({'rule':rule,'queries':points},job.get('control'))
            except ValueError:
                answer={'rule':None,'predictions':[None]*5,'sum':None,'contrast':None}
            output=final(answer)
        value={'status':'completed','model':self.model,'output':output,'usage':{'input_tokens':0,'output_tokens':0},'fixture':True}
        payload={'model':self.model,'input':history,'tools':tools,'store':False,'parallel_tool_calls':False,'max_output_tokens':max_output_tokens}
        with (self.study/'provider.jsonl').open('a',encoding='utf-8') as f:
            for record in ({'event':'request_started','attempt':self.attempt,'worker':worker,'payload':payload,'fixture':True},
                           {'event':'response','attempt':self.attempt,'worker':worker,'response':value,'seconds':0,'fixture':True}):
                f.write(json.dumps(record,ensure_ascii=False)+'\n')
        return value


def fixture(identity):
    start=time.monotonic()
    study=prepare(identity,fixture=True)
    result=run(study,fixture_provider=FixtureProvider(study))
    reg=json.loads((study/'registration.json').read_text())
    model_jobs=[j for j in reg['schedule'] if j['role'] in ('writer','reader','designer','critic')]
    statuses={}
    audits=[]
    for job in model_jobs:
        run_path=study/'units'/job['id']
        r=json.loads((run_path/'result.json').read_text())
        statuses[r['status']]=statuses.get(r['status'],0)+1
        if (run_path/'audit.json').exists():
            audits.append(json.loads((run_path/'audit.json').read_text()))
    if not all(a['pass'] for a in audits) or any(s not in ('completed','budget_rejected','skipped_dependency','injected_crash_after_commit') for s in statuses):
        raise ValueError('offline fixture integrity gate failed')
    evaluated=evaluate(study)
    for row in evaluated['rows']:
        job=row['job']
        if job['role']!='reader':
            continue
        control=job.get('control')
        if job['condition']=='C1':
            assert row['status']=='skipped_dependency' and not row['score']['rule_correct']
        elif control in ('missing','corrupt'):
            assert row['score']['null_fields']==9 and not row['score']['rule_correct']
        elif control=='incompatible':
            assert row['score']['wrong_fields']==1 and not row['score']['rule_correct']
        elif control=='ambiguous':
            assert row['score']['control_expected_correct'] and row['score']['null_fields']==1
        else:
            assert row['score']['all_correct']
    assert evaluated['costs']['api_measurements_available'] is False
    result.update(fixture=True,pass_all=True,statuses=statuses,verified_contexts=len(audits),model_positions=len(model_jobs),seconds=time.monotonic()-start)
    write_json(study/'fixture-result.json',result)
    return study,result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identity')
    args=parser.parse_args()
    path,result=fixture(args.identity)
    print(json.dumps({'study':str(path),**result}),flush=True)
