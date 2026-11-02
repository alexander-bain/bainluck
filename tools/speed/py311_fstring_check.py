"""Flag f-strings that only Python 3.12+ accepts (PEP 701): inside a replacement field,
a string literal using the enclosing f-string's own quote, or a backslash / comment.
Production runs 3.11; ast.parse(feature_version=(3,11)) does NOT catch these.
Usage: py311_fstring_check.py FILE...   exit 1 if any flagged."""
import sys, tokenize, io

def check(path):
    bad = []
    toks = list(tokenize.generate_tokens(io.StringIO(open(path).read()).readline))
    stack = []  # (quote, depth_of_braces)
    for t in toks:
        if t.type == tokenize.FSTRING_START:
            if stack:
                q = stack[-1][0]
                inner = t.string.lstrip("rRfFbBuU")
                if inner.startswith(q) or (len(q) == 1 and inner.startswith(q * 3)):
                    bad.append((t.start[0], "nested f-string reuses the enclosing quote"))
            stack.append((t.string.lstrip("rRfFbBuU"), 0))
        elif t.type == tokenize.FSTRING_END:
            stack.pop()
        elif stack and t.type == tokenize.STRING:
            q = stack[-1][0]
            body = t.string.lstrip("rRbBuU")
            if body.startswith(q) or (len(q) == 1 and body.startswith(q)):
                bad.append((t.start[0], "string literal in a replacement field reuses the enclosing quote"))
            if "\\" in t.string:
                bad.append((t.start[0], "backslash inside a replacement field"))
        elif stack and t.type == tokenize.COMMENT:
            bad.append((t.start[0], "comment inside an f-string"))
    return bad

rc = 0
for p in sys.argv[1:]:
    for line, why in check(p):
        print(f"{p}:{line}: {why}"); rc = 1
sys.exit(rc)
