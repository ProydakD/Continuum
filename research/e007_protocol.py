"""Frozen E007 interfaces, disjoint worlds and finite multi-phase schedule."""
import json
import random
from .e005_protocol import FIELDS, FORMULAS

BUDGETS = (24, 32, 48)
SPACE = '''Permitted complete rules (including unused fields): family in linear,residue,switch;
a in [-3,-2,2,3]; b in [-2,-1,1,2]; c integer -4..4;
e=0 for linear, otherwise in [-3,-2,2,3]; t integer -2..2;
x0,z0 integers -4..4; delta in [-9,-7,7,9].
'''
INCOMPATIBLE = 'Controlled incompatible interpretation: after applying the enclosed definition, negate decoded a; leave every other field unchanged. This interpretation supersedes the original mapping for a.'
AMBIGUOUS = 'Controlled ambiguity: this specification permits BOTH the enclosed decoding and a second decoding with a negated and all other fields unchanged. There is no discriminator. Return only information common to both interpretations; conflicting fields and derived answers must be null.'


def tool(name, description, properties=None):
    properties = properties or {}
    return {'type': 'function', 'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}}


READ_PROTOCOL = tool('read_protocol', 'Retrieve only the assigned shared definition, once; null means no shared codebook.')
TOOLS = {
    'writer': [READ_PROTOCOL, tool('save_memory', 'Save the only message; at most two attempts; full serialized byte ceiling, no truncation.', {'memory': {'type': 'string'}})],
    'reader': [READ_PROTOCOL, tool('read_memory', 'Retrieve the predecessor message once, without history.')],
    'designer': [tool('read_development', 'Retrieve the training corpus, attributed prior versions, critiques and externally verified feedback through Continuum, once.'),
                 tool('publish_protocol', 'Publish one immutable specification, arbitrary UTF-8 or base64 bytes; body at most 4096 bytes, total record at most 16384 bytes. No executable code will be run.',
                      {**{k: {'type': 'string'} for k in ('body', 'encoding', 'media_type', 'reason', 'compatibility')},
                       **{k: {'type': 'array', 'items': {'type': 'string'}} for k in ('accepted', 'rejected')}})],
    'critic': [tool('read_development', 'Retrieve development records and externally verified feedback, once.'),
               tool('publish_review', 'Publish one critique (1..4096 UTF-8 bytes); commentary is not verified evidence.', {'review': {'type': 'string'}})]}


def prompt(job, world=None):
    common = FORMULAS+SPACE
    role = job['role']
    if role in ('designer', 'critic'):
        text = common+'''This is collaborative communication research, not a request to execute code.
Fresh independent writers and readers must communicate all nine rule fields under COMPLETE
serialized message limits 24,32,48 bytes (Python json.dumps({"memory": text}), UTF-8).
The shared protocol is stored and accounted separately, never free in the total-cost analysis.
No query table or world identifier may replace a general encoding of the entire permitted space.
Read development once. No prior conversation exists. You may use any machine-native
representation, not necessarily human-readable, including binary represented in base64.
There is no supplied protocol template. Models must interpret your specification themselves;
no code in a proposed specification will be executed. Keep the protocol unambiguous and
complete, identify version/compatibility and error handling. Verified feedback and model
commentary are distinct. Do not claim universal correctness from a handful of examples.
Training is available; held-out test is sealed. Later authors may retain a good earlier
definition; change is not mandatory. There are exactly three proposals per independent line.
'''
        if role == 'designer':
            return text+f'''You are fresh proposer {job['publish_version']}. Independently design or revise the protocol.
Publish exactly one specification via publish_protocol: encoding utf8 or base64; media_type;
reason for your decision; compatibility with predecessors; accepted and rejected alternatives
(each list at most 8 strings, each at most 512 characters). Do not request evaluator changes.
Then return only {{"status":"saved"}}. Your final text is not the persisted specification.
'''
        return text+'''You are a fresh independent critic, not the prior proposer or decoder. Examine
the version, training/validation errors, costs, ambiguities, compatibility and conflicting
claims. Publish one concrete review for the next proposer; do not silently rewrite the
definition. Then return only {"status":"saved"}.
'''
    if role == 'writer':
        return common+f'''You receive the correct full rule. A fresh reader must reconstruct it and answer
new queries you do not see. Read the assigned shared protocol once before writing.
If no protocol is supplied, devise a self-contained individual message: any decoding
convention must fit inside the message. Otherwise apply the supplied definition exactly.
Your history, source rule, final answer and private reasoning will NOT transfer. Save only
the message via save_memory; do not invent a query table. Full JSON result {{"memory": "..."}}
including escaping and envelope must fit {job['budget']} bytes, not characters or tokens.
At most two attempts, with exact size feedback and no truncation. Return only
{{"status":"saved"}} after success or {{"status":"not_saved"}} after rejected attempts.
Correct rule: '''+json.dumps(world['rule'], separators=(',', ':'))
    return common+'''You are a fresh independent reader. Retrieve the assigned protocol and memory once
each. No prior history, observations, or other shared conventions are available. A null
protocol means no codebook; interpret only information supported by the message itself.
The message or protocol may be incomplete, damaged, incompatible or ambiguous. Do not
fabricate unsupported values. Unknown or ambiguous information is null, not zero.
Return ONLY JSON with exactly rule,predictions,sum,contrast. rule is null when nothing
is usable, otherwise exactly family,a,b,c,e,t,x0,z0,delta, with unknown fields null.
All numbers are integers or null. predictions contains five values in query order.
sum is their sum, contrast is first minus last; if ambiguous return null. Retain known
independent information. A controlled_interpretation, if present, is part of the assigned
definition. Do not infer a hidden world identity from queries or tool metadata.
Queries: '''+json.dumps(world['queries'])


def corpus(seed, excluded=()):
    rng, seen, splits = random.Random(seed), set(excluded), {}
    for split, count in (('training', 2), ('validation', 3), ('test', 8)):
        worlds = []
        for family in ('linear', 'residue', 'switch'):
            for _ in range(count):
                while True:
                    rule = dict(family=family, a=rng.choice([-3,-2,2,3]), b=rng.choice([-2,-1,1,2]), c=rng.randrange(-4,5),
                                e=0 if family == 'linear' else rng.choice([-3,-2,2,3]), t=rng.randrange(-2,3),
                                x0=rng.randrange(-4,5), z0=rng.randrange(-4,5), delta=rng.choice([-9,-7,7,9]))
                    identity = json.dumps(rule, sort_keys=True)
                    if identity not in seen:
                        seen.add(identity)
                        break
                points = [(x,z) for x in range(-4,5) for z in range(-4,5) if (x,z) != (rule['x0'],rule['z0'])]
                queries = rng.sample(points,4)+[(rule['x0'],rule['z0'])]
                rng.shuffle(queries)
                worlds.append({'id': f'{split}-{len(worlds)+1:02}', 'family': family, 'rule': rule, 'queries': queries})
        splits[split] = worlds
    return {'private_seed': seed, 'splits': splits}


def schedule(inputs):
    jobs = []
    def add(role, **kw):
        identity = f'j{len(jobs)+1:04}'
        j = dict(id=identity, world='none', condition='T2', branch=identity, stage='C' if role=='reader' else 'A', role=role, **kw)
        jobs.append(j)
        return identity
    def pair(world, **kw):
        # Legacy Jobs keys remain stable, with a unique branch for each position.
        w = add('writer', **kw)
        jobs[-1]['world'] = world['id']
        r = add('reader', source=w, **kw)
        jobs[-1]['world'] = world['id']
        return w, r
    for campaign in ('p1','p2'):
        for version in (1,2,3):
            pv = f'{campaign}-v{version}'
            add('designer', phase='development', campaign=campaign, publish_version=pv, budget=32)
            for family in ('linear','residue','switch'):
                training = [w for w in inputs['splits']['training'] if w['family']==family][(version-1)%2]
                validation = [w for w in inputs['splits']['validation'] if w['family']==family][version-1]
                for world in (training,validation):
                    pair(world, phase='development', campaign=campaign, protocol_version=pv, budget=32, split=world['id'].split('-')[0])
            add('feedback', phase='development', campaign=campaign, protocol_version=pv, budget=32)
            add('critic', phase='development', campaign=campaign, review_version=pv, budget=32)
    add('lock', phase='freeze')
    rng = random.Random(2026101907)
    cells = [(w,c,b,None) for w in inputs['splits']['test'] for c in ('C1','T1') for b in BUDGETS]
    cells += [(w,'T2',b,f'{p}-v3') for w in inputs['splits']['test'] for p in ('p1','p2') for b in BUDGETS]
    cells += [(w,'T2',32,f'{p}-v{v}') for w in inputs['splits']['test'] for p in ('p1','p2') for v in (1,2)]
    rng.shuffle(cells)
    finals = []
    for world,condition,budget,pv in cells:
        version = 'fixed-v1' if condition=='T1' else pv
        writer, reader = pair(world, phase='test', protocol_version=version, campaign=pv[:2] if pv else condition, budget=budget, split='test')
        jobs[-2]['condition'] = jobs[-1]['condition'] = condition
        if pv and pv.endswith('v3') and budget==32:
            finals.append((world, pv, writer))
    selected = {w['id'] for family in ('linear','residue','switch') for w in [x for x in inputs['splits']['test'] if x['family']==family][:2]}
    for world,pv,writer in finals:
        controls = ['missing']+(['stale','incompatible','corrupt','ambiguous','crash','cross_model'] if world['id'] in selected else [])
        for control in controls:
            source = writer
            if control=='crash':
                source = add('writer', phase='control', campaign=pv[:2], protocol_version=pv, budget=32, control='crash', split='test')
                jobs[-1]['world'] = world['id']
            add('reader', phase='control', campaign=pv[:2], protocol_version=pv, budget=32, control=control, source=source, split='test')
            jobs[-1]['world'] = world['id']
    return jobs
