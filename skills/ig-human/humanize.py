#!/usr/bin/env python3
"""
humanize.py - strip the machine fingerprint out of a draft.

Three passes, in this order:

  1. INVISIBLE   delete or normalise the characters a human keyboard never
                 produces: zero-width joiners, word joiners, soft hyphens,
                 BOMs, Unicode tag characters, non-breaking and narrow spaces.
                 These survive copy-paste and are the most mechanical tell in
                 any generated text.
  2. TYPOGRAPHIC em dash -> comma, en dash -> hyphen, curly quotes -> straight,
                 ellipsis -> three dots, bullet -> hyphen.
  3. LEXICAL     replace the slop lexicon in slop.json with plain words,
                 preserving capitalisation and leaving URLs untouched.

--lang es switches to slop.es.json (castellano, tuteo) and to Spanish-safe
typography: the raya used for dialogue ("—Hola —dijo.") or for an attached
inciso ("mi madre ―que no sabe― lo usa") is correct Spanish and is kept, and
so are « » and the opening marks ¿ ¡. Only the English-style splice spaced on
both sides (" — ") becomes a comma.

Structural tells (rule-of-three, "not just X, it's Y", hashtag walls) are
REPORTED, never auto-rewritten - rewriting a sentence's shape needs judgement,
so that is the model's job, not a regex's.

Usage
  python3 humanize.py draft.txt
  python3 humanize.py draft.txt --report
  pbpaste | python3 humanize.py - --report
  python3 humanize.py draft.txt --json
  python3 humanize.py draft.txt -o clean.txt
  python3 humanize.py borrador.txt --lang es --report
"""

import argparse
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEXICONS = {"en": os.path.join(HERE, "slop.json"),
            "es": os.path.join(HERE, "slop.es.json")}
LEX = LEXICONS["en"]

URL_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+")
SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")

# Per-language behaviour lives here, not in the lexicon: a hand-edited
# --lexicon should change vocabulary, never how a raya or a capital is read.

# Spanish uses the raya (U+2014, or U+2015 in some typesetting) correctly for
# dialogue and for incisos, and there it is always attached to the text on one
# side. What a model adds is the English splice spaced on BOTH sides - the
# strongest GPT-4o tell in Spanish (0.0 per 1k tokens in human text vs 2.9 in
# GPT output). Only that shape is rewritten.
RAYAS = "—―"


def es_splice_dash(ch):
    return re.compile(r"[ \t]+" + re.escape(ch) + r"[ \t]+")


# The connective that follows a dash-turned-comma ("..., also, ...").
SPLICE = {
    "en": re.compile(r",\s*(also|so|still|basically|in the end)\s*,\s*"),
}
# Spanish uses these connectives between commas all the time and correctly
# ("Vino, además, con su hermano"), so the full stop is only earned where the
# comma used to be a spaced dash. That case is fixed in pass_typographic,
# before the dash becomes a comma and the evidence is gone.
ES_DASH_SPLICE = re.compile(r"[ \t]+[—―][ \t]+(además|así que|aun así|básicamente|al final)"
                            r"\s*,\s*", re.IGNORECASE)

# Sentence starts. Spanish needs accented letters and must look through the
# opening ¿ ¡ (and « ") to the first letter, or "¿por qué" never gets fixed.
CAP_START = {
    "en": re.compile(r"(?:^|[.!?]\s+|\n)\s*([A-Za-z])"),
    "es": re.compile(r"(?:^|[.!?]\s+|\n)\s*[¿¡«\"]*([^\W\d_])"),
}
CAP_FIX = {
    "en": re.compile(r"(?:^|(?<=[.!?] )|(?<=[.!?]\n)|(?<=\n))\s*([a-z])"),
    "es": re.compile(r"(?:^|(?<=[.!?] )|(?<=[.!?]\n)|(?<=\n))\s*[¿¡]?([a-záéíóúñü])"),
}


def load_lexicon(path=LEX):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _cp(spec):
    """'U+200B' -> '\\u200b';  'U+E0000-U+E007F' -> (start, end)."""
    if "-" in spec:
        a, b = spec.split("-")
        return (int(a[2:], 16), int(b[2:], 16))
    return int(spec[2:], 16)


def protect_urls(text):
    """Swap URLs for placeholders so no pass rewrites inside a link."""
    found = []

    def stash(m):
        found.append(m.group(0))
        return f"\x00URL{len(found) - 1}\x00"

    return URL_RE.sub(stash, text), found


def restore_urls(text, found):
    for i, url in enumerate(found):
        text = text.replace(f"\x00URL{i}\x00", url)
    return text


def pass_invisible(text, lex):
    """Delete or space-normalise invisible characters. Returns (text, hits)."""
    hits = []
    for entry in lex["invisible"]:
        cp = _cp(entry["cp"])
        if isinstance(cp, tuple):
            pattern = "[" + re.escape(chr(cp[0])) + "-" + re.escape(chr(cp[1])) + "]"
        else:
            pattern = re.escape(chr(cp))
        n = len(re.findall(pattern, text))
        if n:
            hits.append({"name": entry["cp"] + " " + entry["name"], "count": n,
                         "action": entry["action"]})
            text = re.sub(pattern, "" if entry["action"] == "delete" else " ", text)
    # Any remaining Cf (format) character is invisible by definition.
    stray = [c for c in text if unicodedata.category(c) == "Cf"]
    if stray:
        hits.append({"name": "other invisible format chars", "count": len(stray),
                     "action": "delete"})
        text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return text, hits


def pass_typographic(text, lex, lang="en"):
    hits = []
    for entry in lex["typographic"]:
        ch = entry["from"]
        if lang == "es" and ch in RAYAS:
            # Count and rewrite only the spaced splice; dialogue and attached
            # incisos are RAE-correct and stay exactly as written.
            splice = es_splice_dash(ch)
            n = len(splice.findall(text))
            if n:
                hits.append({"name": f"{ch} {entry['name']} (spaced splice)", "count": n,
                             "to": entry["to"].strip() or "(space)"})
                text = ES_DASH_SPLICE.sub(
                    lambda m: ". " + m.group(1)[0].upper() + m.group(1)[1:] + ", ", text)
                text = splice.sub(", ", text)
            continue
        n = text.count(ch)
        if not n:
            continue
        hits.append({"name": f"{ch} {entry['name']}", "count": n, "to": entry["to"].strip() or "(space)"})
        if ch == "—":
            # " word — word " and "word—word" both collapse to a comma + space.
            text = re.sub(r"\s*—\s*", ", ", text)
        elif ch == "–":
            text = re.sub(r"\s*–\s*(?=\d)", "-", text)      # 5–10  -> 5-10
            text = re.sub(r"\s+–\s+", ", ", text)            # used as em dash
            text = text.replace("–", "-")
        else:
            text = text.replace(ch, entry["to"])
    # A comma inserted before existing punctuation reads wrong.
    text = re.sub(r",\s*([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*\n", "\n", text)
    return text, hits


def _match_case(src, repl):
    if not repl:
        return repl
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[0].isupper():
        return repl[0].upper() + repl[1:]
    return repl


def pass_lexical(text, lex, lang="en"):
    """Replace slop words and phrases. Longest first so phrases win."""
    hits = []
    entries = sorted(lex["phrases"] + lex["words"],
                     key=lambda e: len(e["find"]), reverse=True)
    for entry in entries:
        find = entry["find"]
        pattern = re.compile(r"\b" + re.escape(find).replace(r"\ ", r"\s+") + r"\b",
                             re.IGNORECASE)
        found = pattern.findall(text)
        if not found:
            continue
        hits.append({"find": find, "replace": entry["replace"] or "(deleted)",
                     "count": len(found), "family": entry["family"]})
        text = pattern.sub(lambda m: _match_case(m.group(0), entry["replace"]), text)
    # Clean up after deletions. Deleting a whole clause leaves orphaned
    # punctuation behind ("system. ." or a line that now opens on a comma),
    # and that reads worse than the slop did.
    text = re.sub(r"[ \t]{2,}", " ", text)
    if lang == "es":
        # Deleting a sentence-initial connective ("En este sentido, ...")
        # leaves "texto. , sigue" or "¿ qué". Needs the space: "¿Vienes?,
        # preguntó" is correct Spanish and must survive.
        text = re.sub(r"([.!?])[ \t]+,[ \t]*", r"\1 ", text)
        text = re.sub(r"([¿¡])[ \t]+", r"\1", text)
        # A deleted closer inside its marks ("¡Déjamelo en los comentarios!")
        # leaves an empty "¡!".
        text = re.sub(r"[¿¡][?!]+", "", text)
        text = re.sub(r"(?m)[ \t]+$", "", text)
    text = re.sub(r"(?m)^[ \t]*(?:[,.;:]+[ \t]*)+", "", text)
    text = re.sub(r"(?m)^[ \t](?=\S)", "", text)       # one space left by a deletion.
                                                      # Deeper indents are deliberate.
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*([,.;:!?])", r"\1", text)      # an em dash became a comma,
                                                      # then the clause after it went
    text = text.replace("...", "\x00ELL\x00")          # protect real ellipses
    text = re.sub(r"\.\s*\.+", ".", text)
    text = re.sub(r"([!?])\s*\.", r"\1", text)
    text = text.replace("\x00ELL\x00", "...")
    text = re.sub(r"(?m)^[ \t]+$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # An em dash that became a comma, followed by a sentence connective, leaves
    # a splice ("is important, also, it's proof"). Promote it to a full stop.
    if lang in SPLICE:
        text = SPLICE[lang].sub(
            lambda m: ". " + m.group(1)[0].upper() + m.group(1)[1:] + ", ", text)
    return text, hits


def scan_structures(text, lex):
    flags = []
    for s in lex["structures"]:
        try:
            pattern = re.compile(s["regex"], re.MULTILINE)
        except re.error:
            continue
        found = pattern.findall(text)
        if found:
            flags.append({"name": s["name"], "count": len(found), "fix": s["fix"]})
    # Sentence-length uniformity is structural too.
    lens = [len(s.split()) for s in SENT_RE.findall(text) if len(s.split()) > 2]
    if len(lens) >= 4:
        mean = sum(lens) / len(lens)
        var = sum((n - mean) ** 2 for n in lens) / len(lens)
        cv = (var ** 0.5) / mean if mean else 0
        if cv < 0.35:
            flags.append({
                "name": f"Uniform sentence length (variation {cv:.2f})",
                "count": len(lens),
                "fix": "Break one sentence in half. Let another run long. Machines write even.",
            })
    return flags


def restore_capitals(original, text, lang="en"):
    """Deleting an opener leaves the next word lower case.

    Only fix it for writers who capitalise their sentences in the first place:
    a deliberately lower-case voice is a style, not an artefact, and shouting
    over it would be exactly the kind of thing this script exists to stop.
    """
    starts = CAP_START[lang].findall(original)
    if not starts or sum(1 for c in starts if c.isupper()) * 2 < len(starts):
        return text
    return CAP_FIX[lang].sub(lambda m: m.group(0)[:-1] + m.group(1).upper(), text)


def humanize(text, lex, lang="en"):
    raw_for_case = text
    text, urls = protect_urls(text)
    text, inv = pass_invisible(text, lex)
    text, typo = pass_typographic(text, lex, lang)
    text, lexi = pass_lexical(text, lex, lang)
    text = restore_capitals(raw_for_case, text, lang)
    text = restore_urls(text, urls)
    return text.strip() + "\n", {
        "invisible": inv,
        "typographic": typo,
        "lexical": lexi,
        "structures": scan_structures(text, lex),
    }


def render_report(report, out=sys.stderr):
    def head(title):
        print(f"\n{title}\n" + "-" * len(title), file=out)

    total = sum(h["count"] for h in report["invisible"]) \
        + sum(h["count"] for h in report["typographic"]) \
        + sum(h["count"] for h in report["lexical"])

    head("HUMANIZE REPORT")
    print(f"{total} machine artefacts removed, "
          f"{len(report['structures'])} structural tells flagged for rewrite", file=out)

    if report["invisible"]:
        head("1. INVISIBLE CHARACTERS")
        for h in report["invisible"]:
            print(f"  {h['count']:>3}x  {h['name']}  -> {h['action']}", file=out)
    if report["typographic"]:
        head("2. TYPOGRAPHY")
        for h in report["typographic"]:
            print(f"  {h['count']:>3}x  {h['name']}  -> {h['to']}", file=out)
    if report["lexical"]:
        head("3. SLOP LEXICON")
        for h in report["lexical"]:
            print(f"  {h['count']:>3}x  {h['find']}  -> {h['replace']}   [{h['family']}]", file=out)
    if report["structures"]:
        head("4. STRUCTURAL TELLS  (not auto-fixed - rewrite these yourself)")
        for h in report["structures"]:
            print(f"  {h['count']:>3}x  {h['name']}\n        {h['fix']}", file=out)
    if not any(report.values()):
        head("CLEAN")
        print("  Nothing to strip.", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Strip the machine fingerprint out of a draft.")
    ap.add_argument("input", nargs="?", default="-", help="file, or - for stdin")
    ap.add_argument("-o", "--out", help="write cleaned text here instead of stdout")
    ap.add_argument("--report", action="store_true", help="print what changed, to stderr")
    ap.add_argument("--json", action="store_true", help="emit {text, report} as JSON")
    ap.add_argument("--lang", choices=sorted(LEXICONS), default="en",
                    help="language of the draft: en (default) or es (castellano, tuteo)")
    ap.add_argument("--lexicon", help="path to a slop lexicon "
                    "(default: slop.json, or slop.es.json with --lang es)")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    lex = load_lexicon(args.lexicon or LEXICONS[args.lang])
    clean, report = humanize(raw, lex, args.lang)

    if args.json:
        print(json.dumps({"text": clean, "report": report}, indent=2, ensure_ascii=False))
        return
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(clean)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(clean)
    if args.report:
        render_report(report)


if __name__ == "__main__":
    main()
