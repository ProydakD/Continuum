"""E-004: controlled reception, not model-authored memory or rule discovery."""
import json
import random

SEED = 2026101904
BUDGET = 512
TOOLS = [{'type': 'function', 'name': 'read_memory',
          'description': 'Read the only retained synthetic memory from Continuum.',
          'parameters': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}}]


def corpus():
    rng = random.Random(SEED)
    worlds = []
    for family in ('linear', 'residue', 'switch'):
        for _ in range(4):
            rule = dict(family=family, a=rng.choice([-3, -2, 2, 3]), b=rng.choice([-2, -1, 1, 2]),
                        c=rng.randint(-4, 4), e=0 if family == 'linear' else rng.choice([-3, -2, 2, 3]),
                        t=rng.randint(-2, 2), x0=rng.randint(-4, 4), z0=rng.randint(-4, 4),
                        delta=rng.choice([-9, -7, 7, 9]))
            ordinary = [(x, z) for x in range(-4, 5) for z in range(-4, 5)
                        if (x, z) != (rule['x0'], rule['z0'])]
            queries = rng.sample(ordinary, 4)+[(rule['x0'], rule['z0'])]
            rng.shuffle(queries)
            worlds.append({'id': f'w{len(worlds)+1:02}', 'family': family, 'rule': rule, 'queries': queries})
    schedule = [dict(world=w['id'], condition=c, branch=b, stage=f'r{r}')
                for w in worlds for c in ('C1', 'T1') for b in ('intact', 'partial', 'empty') for r in (1, 2)]
    rng.shuffle(schedule)
    return {'seed': SEED, 'worlds': worlds, 'schedule': schedule}


def memory(world, condition, branch):
    if condition not in ('C1', 'T1') or branch not in ('intact', 'partial', 'empty'):
        raise ValueError('unregistered condition/intervention')
    rule = world['rule']
    common = {k: v for k, v in rule.items() if k != 'delta'}
    if condition == 'T1':
        main = json.dumps(common, separators=(',', ':'))
        exception = json.dumps({'delta': rule['delta'], 'depends_on': ['x0', 'z0']}, separators=(',', ':'))
    else:
        main = (f"The base family is {rule['family']}. Parameters: a={rule['a']}, b={rule['b']}, "
                f"c={rule['c']}, e={rule['e']}, t={rule['t']}. The sole exceptional point is "
                f"x0={rule['x0']}, z0={rule['z0']}. Its additive correction is in the exception block.")
        exception = f"At the sole exceptional point, add delta={rule['delta']} to the base value."
    payload = {'common': None if branch == 'empty' else main,
               'exception': exception if branch == 'intact' else None, 'padding': ''}
    length = len(json.dumps(payload).encode('utf-8'))
    if length > BUDGET:
        raise ValueError('synthetic memory exceeds registered byte budget')
    payload['padding'] = ' '*(BUDGET-length)
    assert len(json.dumps(payload).encode('utf-8')) == BUDGET
    return payload


def prompt(world):
    return '''Read memory once with read_memory, then return ONLY one JSON object.
This is a synthetic exact integer function. No observations/history exist outside that memory.
The stored rule is known correct; do not infer absent parameters from priors or query order.
Base families: linear = a*x+b*z+c; residue = a*x+b*z+c+e*(x%3);
switch = a*x+b*z+c+e*I(x+z>=t). Modulo is nonnegative; I is 1 if true, else 0.
At the sole exceptional point (x0,z0), add delta. All other points use the base value.
The two memory blocks contain the only world-specific parameters. Ignore whitespace padding.
Missing exception means delta is unknown, NOT zero: retain known parameters, use null for
delta and any prediction or derived answer depending on it. Empty common means all rule
parameters unknown. Do not guess. A missing parameter unused by the family is still unknown.
Return keys exactly: rule, predictions, sum, contrast. rule is null if common is absent,
otherwise an object with exactly family,a,b,c,e,t,x0,z0,delta (delta may be null).
predictions is a list in query order. sum is their sum; contrast is first minus last.
Unknown values are JSON null. Return known independent answers even when others are unknown.
Queries: '''+json.dumps(world['queries'])


def expected(world, branch):
    if branch == 'empty':
        return {'rule': None, 'predictions': [None]*5, 'sum': None, 'contrast': None}
    r = dict(world['rule'])
    if branch == 'partial':
        r['delta'] = None
    values = []
    for x, z in world['queries']:
        y = r['a']*x+r['b']*z+r['c']
        if r['family'] == 'residue':
            y += r['e']*(x % 3)
        elif r['family'] == 'switch':
            y += r['e']*int(x+z >= r['t'])
        if (x, z) == (r['x0'], r['z0']):
            y = None if r['delta'] is None else y+r['delta']
        values.append(y)
    return {'rule': r, 'predictions': values,
            'sum': None if None in values else sum(values),
            'contrast': None if values[0] is None or values[-1] is None else values[0]-values[-1]}
