"""E-005: author a bounded checkpoint, then reconstruct in a fresh context."""
import json
import random

SEED = 2026101905
BUDGETS = (48, 96, 192)
FIELDS = ('family', 'a', 'b', 'c', 'e', 't', 'x0', 'z0', 'delta')
FORMULAS = '''Base families: linear=a*x+b*z+c; residue=a*x+b*z+c+e*(x%3);
switch=a*x+b*z+c+e*I(x+z>=t). Modulo is nonnegative, I is 1 when true, else 0.
At the sole exceptional point (x0,z0), add delta. Other points use the base.
The world-specific fields are family,a,b,c,e,t,x0,z0,delta; even unused fields are part of the record.
'''
WRITE_TOOLS = [{'type': 'function', 'name': 'save_memory', 'description': 'Save your only checkpoint if its complete serialized read result fits the budget; at most two attempts, no truncation.',
                'parameters': {'type': 'object', 'properties': {'memory': {'type': 'string'}}, 'required': ['memory'], 'additionalProperties': False}}]
READ_TOOLS = [{'type': 'function', 'name': 'read_memory', 'description': 'Retrieve the only retained checkpoint from Continuum, once.',
               'parameters': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}}]


def serialized(memory):
    # Exactly matches the unchanged isolated worker's json.dumps(tool_result).
    return json.dumps({'memory': memory}).encode('utf-8')


def corpus():
    rng = random.Random(SEED)
    worlds = []
    for family in ('linear', 'residue', 'switch'):
        for _ in range(2):
            r = dict(family=family, a=rng.choice([-3, -2, 2, 3]), b=rng.choice([-2, -1, 1, 2]),
                     c=rng.randint(-4, 4), e=0 if family == 'linear' else rng.choice([-3, -2, 2, 3]),
                     t=rng.randint(-2, 2), x0=rng.randint(-4, 4), z0=rng.randint(-4, 4), delta=rng.choice([-9, -7, 7, 9]))
            points = [(x, z) for x in range(-4, 5) for z in range(-4, 5) if (x, z) != (r['x0'], r['z0'])]
            queries = rng.sample(points, 4)+[(r['x0'], r['z0'])]
            rng.shuffle(queries)
            worlds.append({'id': f'w{len(worlds)+1:02}', 'family': family, 'rule': r, 'queries': queries})
    pairs = [dict(world=w['id'], condition=c, branch=f'b{b:03}-r{r}', budget=b, replicate=r)
             for w in worlds for c in ('C1', 'T1') for b in BUDGETS for r in (1, 2)]
    writers = [dict(j, stage='A') for j in pairs]
    readers = [dict(j, stage='C') for j in pairs]
    readers += [dict(world=w['id'], condition=c, branch='control', budget=192, replicate=1, stage='C')
                for w in worlds for c in ('REF', 'EMPTY')]
    rng.shuffle(writers)
    rng.shuffle(readers)
    return {'seed': SEED, 'worlds': worlds, 'schedule': writers+readers}


def writer_prompt(world, condition, budget):
    mode = ('Write an ordinary compact text checkpoint; abbreviations and concise notation are allowed. JSON is not required.'
            if condition == 'C1' else
            'Write a compact structured checkpoint as a JSON object or array. Choose your own keys or encoding.')
    return (FORMULAS+'''You receive the correct complete rule. A fresh reader will get ONLY your saved memory,
the common function definitions, and new queries you do not see. It must reconstruct the nine fields,
then predict and compute a sum and contrast. Your final answer/history/source rule will NOT transfer.
Save the most useful self-contained checkpoint with save_memory. Decoding conventions must fit in it;
there is no external codebook. Do not store answers for imagined queries. You may prioritize if needed.
The byte limit covers the COMPLETE JSON tool result {"memory": "your text"}, including quotes,
escaping and envelope (Python json.dumps defaults, UTF-8). This is not a character/token limit.
At most TWO save attempts. If rejected, the tool reports exact bytes; one repair is allowed.
After accepted save return only {"status":"saved"}. If you cannot save, return {"status":"not_saved"}.
'''+mode+f'\nBudget: {budget} bytes.\nCorrect rule: '+json.dumps(world['rule'], separators=(',', ':')))


def reader_prompt(world):
    return FORMULAS+'''Read memory once, then return ONLY one JSON object. The memory was written by a prior
agent and may be incomplete or wrong. No source observations, prior conversation or other memory exist.
Use its supported information, not priors or query order. Unknown is null, NOT zero. Do not fabricate.
You may interpret compact notation if its meaning is supported; no external codebook is available.
Return exactly rule,predictions,sum,contrast. rule is null if no usable memory, otherwise an object
with exactly family,a,b,c,e,t,x0,z0,delta; unknown fields are null. Numeric values must be integers.
predictions has five entries in query order; sum is their sum and contrast is first minus last.
Any answer requiring unknown information is null. Return known independent information where possible.
Queries: '''+json.dumps(world['queries'])


def reference_memory(world):
    text = json.dumps(world['rule'], separators=(',', ':'))
    if len(serialized(text)) > max(BUDGETS):
        raise ValueError('positive reference does not fit the largest budget')
    return text
