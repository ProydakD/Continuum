"""Fixed human protocol and separate mathematical reference; never shown to T2 designers."""
import itertools
import json
import math

FAMILIES = ('linear', 'residue', 'switch')
FIELDS = ('a', 'b', 'c', 'e', 't', 'x0', 'z0', 'delta')
ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
FAMILY_CODES = 'LRS'
FIXED_SPEC = '''Protocol fixed-v1. A message is exactly 10 ASCII characters: FabcdefghK.
Uppercase F is L=linear,R=residue,S=switch and identifies this protocol version.
The eight decimal digits abcdefgh are ZERO-BASED indices, in order, in these lists:
a: [-3,-2,2,3]; b: [-2,-1,1,2]; c: [-4,-3,-2,-1,0,1,2,3,4];
e: [0] for L, otherwise [-3,-2,2,3]; t: [-2,-1,0,1,2];
x0: [-4,-3,-2,-1,0,1,2,3,4]; z0: [-4,-3,-2,-1,0,1,2,3,4]; delta: [-9,-7,7,9].
K is one decimal digit: (family index L=0,R=1,S=2 plus the SUM of the eight index digits) modulo 10.
Do not store actual signed values instead of indices. Decode each index through its list.
Reject wrong length, non-ASCII digit, unknown family, out-of-range index or wrong checksum.
Checksum detects any single index-digit change that remains in range; it does not detect all swaps or multi-symbol damage.
Never invent missing fields or correct an invalid message silently. This protocol encodes every permitted rule, including unused fields.
'''


def domains(family):
    if family not in FAMILIES:
        raise ValueError('unknown family')
    return ((-3, -2, 2, 3), (-2, -1, 1, 2), tuple(range(-4, 5)),
            (0,) if family == 'linear' else (-3, -2, 2, 3), tuple(range(-2, 3)),
            tuple(range(-4, 5)), tuple(range(-4, 5)), (-9, -7, 7, 9))


def combinations(family):
    return math.prod(map(len, domains(family)))


def indices(rule):
    if set(rule) != {'family', *FIELDS} or any(type(rule[k]) is not int for k in FIELDS):
        raise ValueError('rule schema or scalar type')
    return [values.index(rule[k]) for k, values in zip(FIELDS, domains(rule['family']))]


def fixed_encode(rule):
    family = FAMILIES.index(rule['family'])
    values = indices(rule)
    return FAMILY_CODES[family] + ''.join(map(str, values)) + str((family + sum(values)) % 10)


def fixed_decode(message):
    if not isinstance(message, str) or len(message) != 10 or message[0] not in FAMILY_CODES or any(c not in '0123456789' for c in message[1:]):
        raise ValueError('invalid fixed-v1 framing')
    family_index = FAMILY_CODES.index(message[0])
    family = FAMILIES[family_index]
    values = list(map(int, message[1:9]))
    if int(message[-1]) != (family_index + sum(values)) % 10:
        raise ValueError('fixed-v1 checksum')
    try:
        return dict(family=family, **{k: d[i] for k, d, i in zip(FIELDS, domains(family), values)})
    except IndexError as exc:
        raise ValueError('fixed-v1 index') from exc


def reference_encode(rule):
    family = rule['family']
    rank = 0
    for index, values in zip(indices(rule), domains(family)):
        rank = rank*len(values) + index
    rank += sum(combinations(f) for f in FAMILIES[:FAMILIES.index(family)])
    digits = [(rank >> shift) & 63 for shift in (18, 12, 6, 0)]
    return '0' + ''.join(ALPHABET[d] for d in digits) + ALPHABET[sum(digits) % 64]


def reference_decode(message):
    if not isinstance(message, str) or len(message) != 6 or message[0] != '0':
        raise ValueError('reference framing')
    try:
        digits = [ALPHABET.index(c) for c in message[1:]]
    except ValueError as exc:
        raise ValueError('reference alphabet') from exc
    if sum(digits[:4]) % 64 != digits[4]:
        raise ValueError('reference checksum')
    rank = sum(d << shift for d, shift in zip(digits, (18, 12, 6, 0)))
    for family in FAMILIES:
        count = combinations(family)
        if rank < count:
            break
        rank -= count
    else:
        raise ValueError('reference unused code point')
    values = []
    for domain in reversed(domains(family)):
        rank, index = divmod(rank, len(domain))
        values.append(domain[index])
    return dict(family=family, **dict(zip(FIELDS, reversed(values))))


def all_rules():
    for family in FAMILIES:
        for values in itertools.product(*domains(family)):
            yield dict(family=family, **dict(zip(FIELDS, values)))


def bounds():
    count = sum(combinations(f) for f in FAMILIES)
    return {'rules_by_family': {f: combinations(f) for f in FAMILIES}, 'total_rules': count,
            'minimum_fixed_binary_bits': (count-1).bit_length(), 'log2_cardinality': math.log2(count),
            'fixed_payload_bytes': 10, 'fixed_complete_message_bytes': len(json.dumps({'memory': 'L000000000'}).encode()),
            'reference_payload_bytes': 6, 'reference_complete_message_bytes': len(json.dumps({'memory': '0AAAAA'}).encode()),
            'scope': 'source-rule cardinality only; shared protocol, metadata, checksum and negotiation are additional information/cost'}
