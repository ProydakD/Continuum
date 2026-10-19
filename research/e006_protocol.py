"""E-006: 24 new worlds, stricter serialized budgets, unchanged task semantics."""
import random
from .e005_protocol import FIELDS, READ_TOOLS, WRITE_TOOLS, reader_prompt, reference_memory, serialized, writer_prompt

SEED = 2026101906
BUDGETS = (24, 32, 48)
WORLDS_PER_FAMILY = 8


def corpus():
    rng = random.Random(SEED)
    worlds = []
    for family in ('linear', 'residue', 'switch'):
        for _ in range(WORLDS_PER_FAMILY):
            rule = dict(family=family, a=rng.choice([-3, -2, 2, 3]), b=rng.choice([-2, -1, 1, 2]),
                        c=rng.randint(-4, 4), e=0 if family == 'linear' else rng.choice([-3, -2, 2, 3]),
                        t=rng.randint(-2, 2), x0=rng.randint(-4, 4), z0=rng.randint(-4, 4),
                        delta=rng.choice([-9, -7, 7, 9]))
            points = [(x, z) for x in range(-4, 5) for z in range(-4, 5)
                      if (x, z) != (rule['x0'], rule['z0'])]
            queries = rng.sample(points, 4) + [(rule['x0'], rule['z0'])]
            rng.shuffle(queries)
            worlds.append({'id': f'w{len(worlds)+1:02}', 'family': family, 'rule': rule, 'queries': queries})
    pairs = [dict(world=w['id'], condition=c, branch=f'b{b:03}-r1', budget=b, replicate=1)
             for w in worlds for c in ('C1', 'T1') for b in BUDGETS]
    writers = [dict(j, stage='A') for j in pairs]
    readers = [dict(j, stage='C') for j in pairs]
    readers += [dict(world=w['id'], condition=c, branch='control', budget=192, replicate=1, stage='C')
                for w in worlds for c in ('REF', 'EMPTY')]
    rng.shuffle(writers)
    rng.shuffle(readers)
    return {'seed': SEED, 'worlds': worlds, 'schedule': writers + readers}
