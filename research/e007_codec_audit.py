"""Independent direct-field decoders and exhaustive finite-space verification."""
import json
import time


def independent_fixed(message):
    if len(message) != 10 or message[0] not in 'LRS' or not all('0' <= c <= '9' for c in message[1:]):
        raise ValueError('frame')
    family = {'L': 'linear', 'R': 'residue', 'S': 'switch'}[message[0]]
    f = 'LRS'.index(message[0])
    a, b, c, e, t, x, z, d, check = [ord(c)-48 for c in message[1:]]
    if check != (f+a+b+c+e+t+x+z+d) % 10 or a > 3 or b > 3 or c > 8 or t > 4 or x > 8 or z > 8 or d > 3 or e > (0 if f == 0 else 3):
        raise ValueError('range/checksum')
    return {'family': family, 'a': [-3, -2, 2, 3][a], 'b': [-2, -1, 1, 2][b], 'c': c-4,
            'e': 0 if f == 0 else [-3, -2, 2, 3][e], 't': t-2, 'x0': x-4, 'z0': z-4, 'delta': [-9, -7, 7, 9][d]}


def independent_reference(message):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    if len(message) != 6 or message[0] != '0' or any(c not in alphabet for c in message[1:]):
        raise ValueError('frame')
    d = [alphabet.index(c) for c in message[1:]]
    if sum(d[:4]) % 64 != d[-1]:
        raise ValueError('checksum')
    number = d[0]*262144+d[1]*4096+d[2]*64+d[3]
    if number >= 2099520:
        raise ValueError('unused code')
    f = 0 if number < 233280 else 1 if number < 1166400 else 2
    number -= (0, 233280, 1166400)[f]
    delta_index = number % 4; number //= 4
    z = number % 9; number //= 9
    x = number % 9; number //= 9
    t = number % 5; number //= 5
    e = number % (1 if f == 0 else 4); number //= (1 if f == 0 else 4)
    c = number % 9; number //= 9
    b = number % 4; a = number // 4
    return {'family': ('linear', 'residue', 'switch')[f], 'a': [-3, -2, 2, 3][a],
            'b': [-2, -1, 1, 2][b], 'c': c-4, 'e': 0 if f == 0 else [-3, -2, 2, 3][e],
            't': t-2, 'x0': x-4, 'z0': z-4, 'delta': [-9, -7, 7, 9][delta_index]}


def exhaustive():
    from .e007_codec import all_rules, bounds, fixed_encode, fixed_decode, reference_encode, reference_decode
    start = time.monotonic()
    counts = {'linear': 0, 'residue': 0, 'switch': 0}
    for rule in all_rules():
        fixed, reference = fixed_encode(rule), reference_encode(rule)
        if not (independent_fixed(fixed) == fixed_decode(fixed) == rule == reference_decode(reference) == independent_reference(reference)):
            raise AssertionError('codec counterexample: '+json.dumps(rule))
        if len(json.dumps({'memory': fixed}).encode()) != 24 or len(json.dumps({'memory': reference}).encode()) != 20:
            raise AssertionError('wrong serialized budget')
        counts[rule['family']] += 1
    if counts != {'linear': 233280, 'residue': 933120, 'switch': 933120}:
        raise AssertionError('incomplete enumeration')
    return {'pass': True, 'counts': counts, 'bounds': bounds(), 'seconds': time.monotonic()-start,
            'proof_scope': 'all 2099520 permitted rules, both codecs, independent and production decoding, exact serialized byte lengths; not LLM performance'}


if __name__ == '__main__':
    import sys
    from pathlib import Path
    result = exhaustive()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))
