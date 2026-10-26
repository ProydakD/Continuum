"""Clarify selector syntax without changing the frozen v1 validator or semantics."""
import hashlib

from .reconstruction import INSTRUCTIONS as PARENT_INSTRUCTIONS

INSTRUCTION_PROFILE = "e009-selector-instructions-v2"
PARENT_INSTRUCTIONS_SHA256 = "54fcab15c9c40f767501f77a82332c7d7ff03cbf0620be0f7b2da652650879b5"
BASELINE_SELECTOR_DECLARATION = """A selector is S:{document,pointer} (strict JSON Pointer), or
F:{document,start,end,decode} (zero-based Unicode codepoint offsets; decode=text
or json). Select exact source, with no replacement value/default/search fields."""
SELECTOR_DECLARATION = """Every selector is a FLAT JSON object, never an object wrapped in S or F.
The integer document index selects an entry in the supplied documents array.
Read that entry's format; it determines the selector's exact keys:
- S document: exactly document and pointer. The strict JSON Pointer starts at
  THAT DOCUMENT'S PAYLOAD VALUE, not the surrounding document or request object.
  Empty pointer "" selects the payload root. Do not add /payload or /documents
  before a path. /payload is valid only if the payload itself has that key.
- F document: exactly document, start, end and decode. Its payload is text,
  even if it looks like JSON. Do not use a pointer. Offsets are zero-based
  Unicode codepoints in the decoded payload string: start inclusive, end
  exclusive. They are not UTF-8 bytes, UTF-16 units or positions in serialized
  JSON. Require 0 <= start < end <= payload length; decode is "text" or "json".
  "text" copies the selected substring; "json" parses only that substring.

The following are standalone syntax illustrations, NOT source evidence for the
current request. Never cite their toy payloads in the answer.
S example:
{"payload":{"item":{"id":"demo"}},
 "selector":{"document":0,"pointer":"/item/id"}}

F text example:
{"payload":"α😀z",
 "selector":{"document":0,"start":1,"end":2,"decode":"text"}}

F JSON example:
{"payload":"x=[null,[]]",
 "selector":{"document":0,"start":2,"end":11,"decode":"json"}}

These rules apply to every selector, including all witness lists and expression
selectors. Select actual supplied source, not the examples. Use no replacement
value/default/search fields. Do not repair a source or reinterpret its format."""

if (hashlib.sha256(PARENT_INSTRUCTIONS.encode("utf-8")).hexdigest()
        != PARENT_INSTRUCTIONS_SHA256
        or PARENT_INSTRUCTIONS.count(BASELINE_SELECTOR_DECLARATION) != 1):
    raise ValueError("Frozen selector instruction parent changed")

INSTRUCTIONS = PARENT_INSTRUCTIONS.replace(
    BASELINE_SELECTOR_DECLARATION, SELECTOR_DECLARATION, 1,
)
