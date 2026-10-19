# E-007 — модельные спецификации и история версий

Это сохранённые результаты моделей, а не инструкции исследователю. Спецификации ниже **не исполнялись как код**. Авторство и прохождение реальных MCP-переходов проверены независимо; высказывания моделей о корректности не считаются доказательствами.

Предрегистрационный коммит: `e68564738c03855d2b3ea6222e19fd1ecc946b7e`. SHA-256 необратимой фиксации: `3a2d9c6bf399e642a0249177f33dda308cc0d57b711b91bd2969d36c0eae3e84`.

Все авторы и критики — отдельные свежие контексты gpt-6-sol (идентичность заявлена шлюзом). p1 и p2 не получали историю друг друга или фиксированный T1.

| Версия | Автор | Байты тела | Проверенные правила training/validation | SHA-256 |
|---|---|---:|---:|---|
| p1-v1 | j0001:A | 2846 | 6/6 | `f40b8a08577001056bd2cca50db873e740b2f82216c9d132b3aa20f394d70f72` |
| p1-v2 | j0016:A | 2455 | 5/6 | `86ae1e1616585af9e760c092e03ef47dc028911ac0b421204988f3c7c1a6495c` |
| p1-v3 | j0031:A | 2404 | 6/6 | `6656a6138aa2a6112d475d6f559574580089378b8181c3dd2ae6447fa9d7ef8b` |
| p2-v1 | j0046:A | 1729 | 6/6 | `db355bc72f6764ae9dc8a4fd0cc97e2b5b82aa29a44f863efcdc96c30b2d84a1` |
| p2-v2 | j0061:A | 1966 | 6/6 | `32d726a6fdeee0c947238f8b170015ce6fa9d9ebfd5d8123f5a92a15e8970a1a` |
| p2-v3 | j0076:A | 2128 | 6/6 | `be4657946b7be561aaa1a39a121cce00461c864fe9574108dd7a4010d2e2cf15` |

## Независимое прочтение истории

p1 использует смешанно-позиционный индекс полного правила, три байта и base64url с префиксом A. p2 использует девять символов с позиционными отображениями. Внутри каждой линии синтаксис и смысл сообщения остались прежними от v1 до v3; изменились формулировки и учёт стоимости. p1-v1 ошибочно заявляла 18 байт полного сообщения; фактически 19, в v2 это исправлено. p2 требует 23 байта. Более короткое сообщение p1 относительно REF (20) объясняется в том числе отсутствием отдельной контрольной суммы, а не нарушением нижней границы.

После фиксации протоколов отдельный post-hoc математический перебор всех 2 099 520 допустимых правил подтвердил обратимость обоих отображений. Это доказательство ёмкости схем, **не успешности LLM**. Оно не подавалось авторам/читателям и не влияло на первичные критерии. Источник и код: [E007-POSTHOC-ANALYSIS.md](E007-POSTHOC-ANALYSIS.md).

Новый для экземпляров согласованный формат наблюдался, но новый метод кодирования не установлен. Base64url — существующий стандарт, а не изобретение данной линии: [RFC 4648, раздел 5](https://www.rfc-editor.org/rfc/rfc4648#section-5). Это ограниченная классификация наблюдаемых схем, не исчерпывающий патентный/литературный поиск.

## p1-v1

Автор: `j0001:A`; критик: `j0015:A`.

**Причина (заявление автора):** A fixed-radix index stores all nine fields, including unused values, in three bytes; base64url plus a version marker leaves ample headroom under the strictest serialized limit without relying on escape behavior or a finite training-world table.

**Совместимость (заявление автора):** First version A; no predecessors or implicit legacy compatibility. Future versions must use a distinct prefix.

**Принятые альтернативы:** ["Mixed-radix enumeration over every permitted field with explicit validation of family/e relationship.", "Three-byte big-endian integer encoded as four unpadded base64url symbols and an ASCII version prefix.", "Explicit invalid-message rejection and separate shared-protocol cost accounting."]

**Отвергнутые альтернативы:** ["Query-response lookup or training-world identifier: cannot represent the entire permitted space.", "Verbose decimal or JSON-in-JSON field listing: risks the 24-byte complete-message limit.", "Implicit defaulting of unused fields: loses part of the record."]

### Тело сохранённой спецификации

````text
Protocol A1 (version marker `A`; applies to the complete rule space in the prompt). The sole transmitted memory is exactly FIVE ASCII characters: literal capital `A` followed by exactly FOUR unpadded base64url characters. The base64url alphabet is `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_`; use standard base64 sextet order, without padding. The four characters encode exactly THREE bytes, interpreted as one unsigned 24-bit BIG-ENDIAN integer N. Do not transmit explanatory text or other fields in memory.

Form N by mixed-radix indexing the nine fields in this precise order: family, a, b, c, e, t, x0, z0, delta, with radices respectively 3,4,4,9,5,5,9,9,4. Index each field from zero in these ordered lists: family [linear,residue,switch]; a [-3,-2,2,3]; b [-2,-1,1,2]; c [-4,-3,-2,-1,0,1,2,3,4]; e [0,-3,-2,2,3]; t [-2,-1,0,1,2]; x0 [-4,-3,-2,-1,0,1,2,3,4]; z0 [-4,-3,-2,-1,0,1,2,3,4]; delta [-9,-7,7,9]. Starting with N=0, for each field in the given order replace N by N times that field's radix plus its index. Write the resulting integer as exactly three big-endian bytes (including leading zero bytes), then base64url-encode those bytes. Prepend `A`. The permitted combinations yield 0 <= N < 3,499,200, which fits in 24 bits. Even if a field does not affect the base formula (e.g. t in linear/residue), encode its actual record value; never omit it.

Decoder: require exactly five ASCII characters, prefix `A`, and four canonical base64url characters; decode to exactly three bytes and big-endian N. Require N < 3,499,200. Recover field indices by successively taking N modulo the radices in REVERSE field order (delta,z0,x0,t,e,c,b,a,family), replacing N by its integer quotient at each step. Map indices through the ordered lists above. Check e=0 iff family=linear; otherwise e must be one of -3,-2,2,3. Any failed check, unexpected prefix/length/alphabet/padding/noncanonical encoding, or absent memory is an invalid message: report decoding failure rather than guess a rule. No legacy-version fallback.

Example: linear, a=-3, b=-2, c=-4, e=0, t=-2, x0=-4, z0=-4, delta=-9 encodes as `AAAAA` (prefix plus four base64url A's). After decoding, use the prompt's linear/residue/switch formulas, nonnegative modulo and inclusive switch threshold, then add delta ONLY at (x0,z0). Writer sends `{"memory":"<five-character-memory>"}`; the quoted placeholder is replaced by the five literal characters. This is a general indexing of permitted records, not a query lookup or world identifier. Python json.dumps with its default separators yields 18 UTF-8 bytes for every message (13 bytes framing plus five ASCII bytes), satisfying each 24/32/48-byte COMPLETE limit. Shared protocol text must be charged separately in total-cost comparisons: for K messages, total is shared-protocol byte cost plus 18K, not just 18K.
````

### Независимый экземпляр-критик (его выводы — модельные утверждения)

````text
p1-v1/A1 is a complete, unambiguous mixed-radix encoding of the nine permitted fields (including unused t), with explicit version prefix, canonical base64url checks, rejection of invalid family/e combinations, and no legacy fallback. Externally verified feedback reports 6/6 correct training/validation cases (two per family), not exhaustive correctness and not held-out results. Concrete cost error: Python json.dumps({'memory':'AAAAA'}) with DEFAULT separators produces '{"memory": "AAAAA"}', which is 19 UTF-8 bytes (14 framing + 5), NOT the claimed 18 (13 framing + 5); 18 applies only to compact separators=(',',':'). Fix the text's default-separator count and total-cost formula to shared protocol UTF-8 bytes + 19K for default serialization (or explicitly require and account for compact serialization). Both 18 and 19 remain below all three 24/32/48 limits. Retain the valid encoding if desired; do not equate six passing examples with universal verification. Measure and include the shared definition's full UTF-8 size separately when making total-cost claims.
````

## p1-v2

Автор: `j0016:A`; критик: `j0030:A`.

**Причина (заявление автора):** Retain the six-case externally verified A1 wire representation without asserting held-out or universal correctness; correct the reviewed default-json framing arithmetic from 18 to 19 bytes, and explicitly charge the shared specification.

**Совместимость (заявление автора):** p1-v2 preserves p1-v1 A1 message encoding and decoding byte-for-byte; this revision corrects only the cost statement and clarifies canonical validation. Other prefixes are unsupported.

**Принятые альтернативы:** ["General mixed-radix encoding of all nine fields, including unused fields.", "Five-character A1 memory and strict decoding with an invalid-message outcome.", "Correct default json.dumps complete-message count of 19 UTF-8 bytes and explicit shared-protocol accounting."]

**Отвергнутые альтернативы:** ["Changing the already tested A1 wire format just to change its prose revision.", "Training-world IDs, query lookup tables, or default values for unused fields.", "Claiming universal or held-out success from six externally verified training/validation cases."]

### Тело сохранённой спецификации

````text
Protocol A1, specification revision p1-v2. Wire format is unchanged from p1-v1. Send memory as exactly five ASCII characters: uppercase `A` followed by four unpadded base64url characters (alphabet `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_`, standard base64 bit ordering). The suffix represents exactly three bytes, interpreted as an unsigned big-endian integer N. No whitespace, padding, or other text in memory.

Encode the COMPLETE nine-field record by mixed radix. Fields in order: family,a,b,c,e,t,x0,z0,delta. Their respective ordered value lists are [linear,residue,switch], [-3,-2,2,3], [-2,-1,1,2], [-4,-3,-2,-1,0,1,2,3,4], [0,-3,-2,2,3], [-2,-1,0,1,2], [-4,-3,-2,-1,0,1,2,3,4], [-4,-3,-2,-1,0,1,2,3,4], [-9,-7,7,9]. Their respective radices are 3,4,4,9,5,5,9,9,4. Start N=0; for each field in order, replace N with N*radix + its zero-based index in that field's list. Convert N to exactly three big-endian bytes, including leading zeros, encode with base64url without padding, and prepend `A`. Encode actual unused fields, including t for linear and residue: do NOT infer defaults. Example: the all-first-index record encodes as `AAAAA`.

Decode by requiring the exact length, prefix and alphabet; base64url-decode the four suffix characters into exactly three bytes and require that re-encoding those bytes gives the identical four characters. Interpret bytes as N and require N<3499200. Starting with delta, then z0,x0,t,e,c,b,a,family, repeatedly obtain an index as N modulo that field's radix and replace N with floor(N/radix); map indices to lists above. Require the final quotient zero. Require e=0 for linear and e in [-3,-2,2,3] for residue or switch. Any violation, missing memory, or unknown prefix is a decoding error: do not guess, repair, or fall back to a different version.

Use the decoded rule exactly as in the task: base a*x+b*z+c, plus e*(x%3) for residue (nonnegative remainder), or plus e when x+z>=t for switch; add delta only when (x,z)=(x0,z0). This indexes the complete permitted rule space, not particular worlds or queries. JSON serialization is separate from memory: Python json.dumps({"memory": text}) with default separators has 19 UTF-8 bytes for these five-ASCII-character memories, meeting 24/32/48. Shared protocol cost is NOT free: for K messages, total bytes = UTF-8 byte length of this shared specification + 19*K (assuming this is the shared specification and default serialization).
````

### Независимый экземпляр-критик (его выводы — модельные утверждения)

````text
p1-v2/A1 retains the p1-v1 wire format and corrects its default-json cost: each five-ASCII-character memory serializes to 19 UTF-8 bytes with Python's default json.dumps({"memory": text}), below 24/32/48. Its ordered radices multiply to 3,499,200 (<2^24), and the family/e validity check excludes impossible combinations while preserving all nine fields, including unused t. External feedback verifies 5/6 p1-v2 training/validation cases; validation-08 (`AKtgi`, reader j0028) has status failed, lineage_verified=false, answer=null, and nine null fields. This is NOT evidence of a wrong decoded rule or arithmetic error, nor grounds to claim 6/6 or universal success. Investigate this specific failed reader/lineage if diagnostics are available; retry or test independently rather than silently changing an otherwise coherent encoding. p1-v1 separately has 6/6 verified examples but still no exhaustive or sealed-test result. If retaining A1, explicitly state byte-for-byte compatibility and reject unknown prefixes; if changing its wire representation, use a distinct prefix and make incompatibility explicit. The shared specification is separately billable: report its actual UTF-8 length before making numerical total-cost comparisons (total = shared-spec bytes + 19K for K default-serialized messages), not just the per-message charge.
````

## p1-v3

Автор: `j0031:A`; критик: `j0045:A`.

**Причина (заявление автора):** Retain compact complete-record A1 encoding and its 19-byte default-JSON message cost; previous feedback includes verified successes but also one reader/lineage failure with no decoded answer, which does not establish an encoding defect. State shared-specification cost separately and make no held-out claim.

**Совместимость (заявление автора):** p1-v3 preserves p1-v1 and p1-v2 A1 wire encoding byte-for-byte. Only prefix A is recognized; no other-version fallback.

**Принятые альтернативы:** ["General mixed-radix encoding of all nine fields, even fields unused by a particular family.", "Three-byte unsigned big-endian payload and five-ASCII-character versioned base64url memory.", "Strict decoding, family/e validation, explicit cost accounting and no extrapolation from limited feedback."]

**Отвергнутые альтернативы:** ["Query lookup tables and world identifiers rather than general rule encoding.", "Omitting or defaulting unused t or e fields.", "Changing the established A1 wire format without evidence of a format defect.", "Interpreting a failed reader with null answer as proof of wrong decoded arithmetic."]

### Тело сохранённой спецификации

````text
A1 wire protocol, specification revision p1-v3. This is byte-for-byte the p1-v1/p1-v2 A1 wire format. Memory is exactly five ASCII characters: uppercase A followed by four unpadded base64url characters, using alphabet ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_ and standard base64 bit order. The suffix encodes exactly three bytes, interpreted as unsigned big-endian integer N. No other characters are allowed.

Encode ALL nine actual record fields, in order family,a,b,c,e,t,x0,z0,delta. Their ordered value lists are respectively [linear,residue,switch], [-3,-2,2,3], [-2,-1,1,2], [-4,-3,-2,-1,0,1,2,3,4], [0,-3,-2,2,3], [-2,-1,0,1,2], [-4,-3,-2,-1,0,1,2,3,4], [-4,-3,-2,-1,0,1,2,3,4], [-9,-7,7,9]. Their radices are 3,4,4,9,5,5,9,9,4. Validate input values and require e=0 for linear, e in [-3,-2,2,3] otherwise. Start N=0 and, for each field in the stated order, set N=N*radix+its zero-based position in its list. Convert N to exactly three big-endian bytes, including leading zeros; base64url-encode without padding and prepend A. Never substitute defaults for unused fields (including t in linear/residue). All-first-position record encodes AAAAA.

Decode only exact five-character ASCII memories with prefix A. Decode suffix as three bytes, reject if its base64url re-encoding is not exactly the suffix; reject if N>=3499200. In reverse field order delta,z0,x0,t,e,c,b,a,family, recover each index as N modulo its radix, then replace N with floor(N/radix); map through the lists. Require final quotient zero and valid family/e pairing. Missing, malformed, unknown-version, or invalid messages are errors; never guess or use a legacy fallback. For predictions use a*x+b*z+c; add e*(x%3) for residue, where remainder is nonnegative; add e for switch iff x+z>=t; then add delta iff (x,z)=(x0,z0). Linear has no e contribution.

Send only the memory text in the memory field. Default Python json.dumps({"memory": text}) yields 19 UTF-8 bytes per five-character memory, meeting the 24/32/48 complete-message limits. Account for the shared specification separately: for K messages total cost is shared-specification UTF-8 byte count plus 19*K (and include any separately charged protocol metadata where applicable). This is a general encoding of all permitted records, not a world identifier or query lookup. Training/validation feedback is not exhaustive or held-out verification.
````

### Независимый экземпляр-критик (его выводы — модельные утверждения)

````text
p1-v3 retains A1 byte-for-byte from p1-v1/v2; its nine-field mixed-radix lists, 3-byte big-endian/base64url wire format, family/e validation, unused-field preservation, strict rejection, and 19-byte default-json message charge are coherent. Verified p1-v3 feedback is 6/6 correct on its sampled training/validation cases, but this does not resolve p1-v2's validation-08 failure: the same wire format's `AKtgi` case (reader j0028) has status failed, lineage_verified=false, answer=null, nine null fields; it supplies no evidence of misdecoding or bad arithmetic and must not be described as fixed by the p1-v3 prose revision. Next proposer: retain A1 unless concrete diagnostics identify a defect; if possible independently retest `AKtgi` with a fresh reader and distinguish infrastructure/lineage failure from decoder failure. Report actual UTF-8 byte count of the chosen shared specification, not only the formula shared-spec bytes + 19K, when comparing total costs; account for any charged metadata. Clearly separate verified sampled outcomes from universal or sealed-test claims, and retain explicit compatibility/rejection of unknown prefixes.
````

## p2-v1

Автор: `j0046:A`; критик: `j0060:A`.

**Причина (заявление автора):** A position-coded 9-character ASCII record preserves every field, including unused t, with simple independent symbol maps; its 23-byte serialized footprint meets the strictest limit without binary/base64 complexity.

**Совместимость (заявление автора):** Standalone P2V1; no predecessor definitions were supplied. Not backward-compatible with any unspecified alternate encoding. Both parties must agree on this shared P2V1 specification separately from the memory.

**Принятые альтернативы:** ["Direct positional encoding of every one of the nine fields, including unused fields.", "Validation before decoding and explicit no-guess handling of absent or invalid data."]

**Отвергнутые альтернативы:** ["World IDs, training-world lookup tables, and query tables cannot represent the complete permitted rule space.", "Variable-width signed decimal fields or JSON objects in memory exceed the tight 24-byte serialized limit.", "Leaving unused t implicit loses information required by the complete rule."]

### Тело сохранённой спецификации

````text
Protocol P2V1 / nine-field decimal-symbol record. A writer who knows the complete rule sends a memory string of exactly nine ASCII characters, without whitespace, quotes within the string, prefix, or suffix. Character positions 1–9 (one-based) encode family, a, b, c, e, t, x0, z0, delta, respectively. Family is L=linear, R=residue, S=switch. The single-digit maps for a, b, and delta are, respectively, 0,1,2,3 -> (-3,-2,2,3), (-2,-1,1,2), and (-9,-7,7,9). For c, digit 0..8 means integer digit minus 4. For e, 0,1,2,3,4 -> (0,-3,-2,2,3); L requires e digit 0, whereas R and S require digits 1..4. For t, digit 0..4 means digit minus 2. For x0 and z0, each digit 0..8 means digit minus 4. All digits mentioned are literal ASCII decimal characters, with no sign. Even when t does not affect the family's formula, encode and decode its actual recorded value; do not substitute a default. Compute y = a*x+b*z+c, plus e*(nonnegative x modulo 3) for R, or plus e when x+z>=t for S, then add delta if and only if x=x0 AND z=z0. L uses only the linear base. Readers validate exact length, ASCII symbol ranges, and the family/e constraint before decoding. If malformed, truncated, or any field is unknown, do not silently repair, guess unused fields, or treat it as a world ID: report inability to decode and seek a complete valid record. No queries or finite training table are required for decoding. For Python json.dumps({"memory": text}) with default ASCII characters, nine unescaped string characters yield exactly 23 UTF-8 bytes, satisfying 24, 32, and 48 byte limits. Version P2V1 is specified here, not transmitted as part of each memory string; readers using this protocol interpret all valid nine-character records as P2V1.
````

### Независимый экземпляр-критик (его выводы — модельные утверждения)

````text
P2V1 is a sound candidate to retain: its positional maps cover all nine fields (including unused t), family/e validity is explicit, and nine ASCII characters serialize as 23 UTF-8 bytes in Python json.dumps({"memory": text}), meeting all three limits. The six externally verified training/validation reads have zero reported field or arithmetic errors, but do not establish correctness over the full permitted space or sealed test. Version is only out-of-band: a reader must be configured for exactly P2V1, since the nine-character memory cannot identify a competing protocol; keep this compatibility requirement explicit. The current error rule correctly rejects malformed/unknown input rather than guessing. For the next proposal, retain the definition unless changing it for a demonstrated reason, and request/check independent edge cases absent from verified feedback (negative deltas -9/-7, residue e=+2/+3, t=-2, and negative x modulo), including unused fields and strict rejection of invalid family/e combinations. Do not describe those prospective checks as verified results.
````

## p2-v2

Автор: `j0061:A`; критик: `j0075:A`.

**Причина (заявление автора):** Retain the prior simple full-field encoding: independent verified feedback reports six successful training/validation cases, not universal correctness or sealed-test results. The unchanged nine-character wire record meets the strictest budget while preserving unused fields and allowing independent readers to validate records.

**Совместимость (заявление автора):** P2V2 is fully wire- and semantics-compatible with P2V1: every P2V1 valid memory decodes identically and conversely. Version selection is out-of-band through the separately accounted shared protocol, not an extra memory character; unrelated encodings are not automatically compatible.

**Принятые альтернативы:** ["Retain the nine-position ASCII representation and exact P2V1 maps for all nine fields.", "Validate family/e consistency and every symbol before decoding, including unused t.", "State negative-x modulo and exceptional-point arithmetic explicitly."]

**Отвергнутые альтернативы:** ["A version marker in the memory would exceed the 24-byte serialized limit if added to nine characters.", "Case identifiers, query tables, or training-world lookups cannot cover the complete permitted space.", "Implicit/default unused t or inferred missing fields lose required information.", "Claiming sealed-test or universal correctness from the six verified examples."]

### Тело сохранённой спецификации

````text
P2V2: nine-character positional memory; wire-compatible with P2V1. The writer transmits exactly nine ASCII characters as the memory string, with no whitespace, punctuation, prefix, or suffix. One-based character positions are family, a, b, c, e, t, x0, z0, delta. Family: L=linear, R=residue, S=switch. At position a: digits 0,1,2,3 mean -3,-2,2,3. At position b: digits 0,1,2,3 mean -2,-1,1,2. At position c: digits 0 through 8 mean digit's integer value minus 4. At position e: digits 0,1,2,3,4 mean 0,-3,-2,2,3; L requires digit 0, whereas R and S require digits 1 through 4. At position t: digits 0 through 4 mean digit's value minus 2. At each of positions x0 and z0: digits 0 through 8 mean digit's value minus 4. At position delta: digits 0,1,2,3 mean -9,-7,7,9. Every digit is a single literal ASCII digit, not a signed or multi-digit number. Preserve the actual value of t for L and R; it is a required recorded field even though the corresponding base formulas do not use it. Likewise preserve e=0 for L. Decode all nine fields by these maps. For any query (x,z), evaluate the linear base a*x+b*z+c for L; add e*(x modulo 3), taking modulo in {0,1,2}, for R; or add e if x+z>=t and 0 otherwise for S. Finally add delta if and only if both x=x0 and z=z0. A reader must reject any memory not exactly nine ASCII characters obeying all position ranges and the family/e constraint, including missing, truncated, or malformed records; do not infer unknown fields, silently repair, or consult a world/query table. Report inability to decode and seek a complete valid record. The version is agreed through this shared specification rather than embedded in memory; P2V1 and P2V2 use identical wire syntax and field semantics. Nine ASCII characters yield 23 UTF-8 bytes under default Python json.dumps({"memory": text}), meeting each of the 24, 32 and 48 byte serialized limits. This encoding covers the entire permitted field space without case-specific references.
````

### Независимый экземпляр-критик (его выводы — модельные утверждения)

````text
P2V2 can be retained unchanged: its nine ASCII positions explicitly encode all nine fields, including unused t; the family/e restrictions and invalid-record rejection are clear, and its exact maps and semantics are wire-compatible with P2V1. The externally verified P2V2 feedback reports 6/6 correct training/validation reads (zero reported field or arithmetic errors); P2V1 separately reports 6/6. These are not exhaustive coverage or sealed-test evidence. Nine ASCII memory characters cost 23 UTF-8 bytes under the specified default json.dumps({"memory": text}), so each message meets 24/32/48; 23 is NOT the total cost: count the separately stored shared protocol and its amortization explicitly in any total-cost claim. Version agreement is out-of-band: a reader without the shared P2V1/P2V2 specification cannot discover the version from the record; identical wire mappings make those two versions mutually compatible, but not arbitrary other protocols. No conflicting claims are apparent in the two definitions, though calling the scheme universally validated would conflict with the limited feedback scope. For the final proposal, preserve exact maps and reject malformed ASCII/range/family-e combinations without guessing; if offering additional checks, prioritize delta=-9/-7 (none in verified examples), negative-x modulo with positive residue e, and unused t at its endpoints, and distinguish such suggested tests from externally verified results.
````

## p2-v3

Автор: `j0076:A`; критик: `j0090:A`.

**Причина (заявление автора):** Retain the exact predecessor maps: externally verified feedback reports six successful training/validation cases per predecessor, but does not prove correctness for all rules or sealed tests. Full-field direct encoding leaves one byte headroom at the tightest serialized limit and avoids case-specific references. Clarify protocol accounting and error handling.

**Совместимость (заявление автора):** P2V3 has identical valid memory strings, maps, and query semantics to P2V1 and P2V2. Readers and writers must share one of these compatible specifications out of band; arbitrary unknown formats cannot be autodetected from a nine-character memory.

**Принятые альтернативы:** ["Keep prior nine-position mapping exactly, including unused t and explicit e=0 for linear.", "Reject all invalid lengths, non-ASCII symbols, out-of-range digits, and inconsistent family/e combinations.", "Distinguish the 23-byte serialized memory cost from separately accounted shared-protocol storage."]

**Отвергнутые альтернативы:** ["Version prefixes in the memory would make this nine-symbol encoding exceed the 24-byte serialized limit.", "World IDs, query tables, or inference of unused fields cannot encode every permitted complete rule.", "Do not equate limited externally verified cases with universal correctness or sealed-test evidence."]

### Тело сохранённой спецификации

````text
P2V3 — nine-character complete-rule memory, wire- and semantics-compatible with P2V1 and P2V2. The shared protocol version is agreed out of band; no version character appears in memory. Writer: obtain all nine actual world-specific fields, including unused ones, and transmit exactly nine unescaped ASCII characters as the memory string, without spaces, quotes inside the string, or other characters. Positions 1–9 (one-based): family, a, b, c, e, t, x0, z0, delta. Maps (literal single ASCII digits unless otherwise stated): family L=linear, R=residue, S=switch; a digits 0,1,2,3 -> -3,-2,2,3; b digits 0,1,2,3 -> -2,-1,1,2; c digits 0..8 -> digit value minus 4; e digits 0,1,2,3,4 -> 0,-3,-2,2,3; t digits 0..4 -> digit value minus 2; x0 and z0 digits 0..8 -> digit value minus 4 each; delta digits 0,1,2,3 -> -9,-7,7,9. L must have e digit 0; R and S must have e digit 1..4. Always encode t's actual value even for L and R, where t is unused; L's e=0 is explicitly encoded. Reader: validate exactly nine ASCII characters, the allowed symbols at each position, and family/e consistency, then invert these maps to recover all nine fields. On any missing, malformed, truncated, or incompatible memory, do not guess or repair, assume a default for an unused field, or use a world ID/table: report that decoding is impossible and request a complete valid record. For queries (x,z), start with a*x+b*z+c. For R add e*(x modulo 3), where remainder is always 0, 1 or 2 even for negative x. For S add e exactly when x+z>=t. L adds neither term. At precisely (x0,z0), add delta to the base result, including when that point is a query. These positional maps cover every permitted complete rule, not merely training examples. Nine ASCII memory characters serialize as 23 UTF-8 bytes under default Python json.dumps({"memory": text}), meeting all three per-message limits (24,32,48). The separately stored shared specification consumes bytes too: any total-cost calculation must separately count its stored size (and explicitly specify how it is amortized); 23 bytes is only the serialized message cost, not total communication cost.
````

### Независимый экземпляр-критик (его выводы — модельные утверждения)

````text
P2V3 is a reasonable final definition to retain: its explicit nine-position maps encode all nine actual fields, including unused t, and its permitted symbols/family–e constraint give a one-to-one representation of the stated rule space. The claimed P2V1/P2V2 compatibility follows from the published identical maps and semantics, but requires out-of-band agreement: a syntactically valid record from an unrelated protocol cannot be detected as incompatible on its own. Keep rejecting malformed/partial records rather than guessing. Externally verified P2V3 feedback reports 6/6 correct training/validation reads with zero reported field or arithmetic errors; this is not exhaustive proof and says nothing about sealed tests. Specifically P2V3 validation-06 checks delta=-7 and positive residue e with negative x, but the six cases do not check delta=-9; avoid claiming those untested edges were verified. Nine ASCII symbols cost 23 bytes under the specified json.dumps wrapper and fit 24/32/48; this is per-message only. A total-cost comparison must add the separately stored shared specification's actual UTF-8 byte size and declare the amortization across messages. No contradiction in the three published definitions is apparent; do not alter exact mappings merely for novelty. If further checks are possible, prioritize delta=-9, t endpoints as unused fields, family/e invalid-record rejection, and limit=24 boundary; label new checks as prospective until externally verified.
````
