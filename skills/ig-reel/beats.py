#!/usr/bin/env python3
"""
beats.py - turn a Reel script into a timed beat sheet before you record it.

Estimates how long each line takes to say, stacks them into timecodes, and
flags the four things that kill a Reel in the edit: a hook that runs past the
three-second mark, a beat long enough for the viewer to leave, a run of lines
with nothing concrete in them, and a total length that does not match what you
said you were making.

The timings are an estimate from word count at a words-per-minute rate. They
are close enough to plan an edit and not a substitute for recording it. Set
your own rate with --wpm once you have timed yourself reading a script out
loud: most people land between 150 and 200, and the default here is 165.

With --lang es the clock is syllables, not words, because Spanish words run
long and Spanish is spoken faster per syllable than English (7.82 vs 6.19
syllables a second read aloud, Pellegrino et al. 2011). The default of 5.2
syllables a second is the English default scaled by that same ratio. Time
yourself and set --sps: syllables in a script you read, divided by seconds.

Usage
  python3 beats.py script.txt
  python3 beats.py script.txt --target 30
  python3 beats.py script.txt --wpm 185 --target 45
  pbpaste | python3 beats.py -
  python3 beats.py script.txt --json
  python3 beats.py guion.txt --lang es --target 30
  python3 beats.py guion.txt --lang es --sps 5.8
"""

import argparse
import json
import re
import sys

WORD_RE = re.compile(r"[A-Za-z0-9$%'’-]+")
SENT_RE = re.compile(r"[^.!?]+[.!?]*")
CONCRETE_RE = re.compile(r"\$\s?\d|\b\d[\d,.]*\b|(?<!^)\b[A-Z][a-z]{2,}\b", re.MULTILINE)
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "with", "that", "this", "it", "is", "are", "was", "were", "be", "been",
    "you", "your", "i", "my", "me", "we", "our", "they", "them", "he", "she",
    "so", "just", "not", "no", "do", "did", "does", "have", "has", "had",
    "will", "can", "at", "as", "by", "from", "out", "up", "off", "one", "all",
}

HOOK_WINDOW = 3.0        # seconds. Past this, the thumb has already decided.
MAX_BEAT = 4.0           # seconds on one idea with no change on screen.
ABSTRACT_RUN = 3         # beats in a row with nothing checkable in them.

# Spanish. Number words ("dos", "mil") are deliberately not stopwords: a hook
# and a last line that share "mil" do loop.
ES = {
    "word_re": re.compile(r"[^\W_][\w$%€'’-]*|[$€]\s?\d[\d.]*"),
    "concrete_re": re.compile(r"[$€]\s?\d|\d\s?€|\b\d[\d,.]*\b"
                              r"|(?<!^)(?<![¿¡])\b[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,}\b", re.MULTILINE),
    "stopwords": {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "lo", "al", "del",
        "y", "e", "o", "u", "pero", "si", "de", "a", "en", "con", "por", "para",
        "sin", "sobre", "que", "qué", "este", "esta", "esto", "ese", "esa", "eso",
        "es", "son", "era", "fue", "ser", "está", "están", "estar", "hay",
        "tú", "tu", "tus", "te", "ti", "yo", "mi", "mis", "me", "nos", "os",
        "se", "su", "sus", "le", "les", "ya", "no", "ni", "muy", "más", "como",
        "cuando", "donde", "también", "solo", "todo", "todos", "toda", "todas",
        "hacer", "haz", "has", "he", "ha", "tiene", "tienes", "puedes", "vas",
        "voy", "va", "así", "pues", "porque",
    },
}


def words(text, lang="en"):
    # "$18,000" is one word when it is spoken, so it is one word here too.
    if lang == "es":
        return ES["word_re"].findall(re.sub(r"(?<=\d)\.(?=\d)", "", text))
    return WORD_RE.findall(re.sub(r"(?<=\d),(?=\d)", "", text))


def clock(lang, wpm, sps):
    """(units of a line, units per second, unit name) for the language."""
    if lang == "es":
        from syllables import count
        return count, sps, "syllables"
    return (lambda t: len(words(t))), wpm / 60.0, "words"


def pretty(token, sep=","):
    """Put the thousands separator back for display."""
    return re.sub(r"(\d)(?=(\d{3})+$)", r"\1" + sep, token)


def tc(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:04.1f}"


def split_beats(raw, wps, units=None):
    """One line is one beat, unless a line is too long to be one."""
    units = units or (lambda t: len(words(t)))
    beats = []
    for line in [l.strip() for l in raw.splitlines()]:
        if not line:
            continue
        if units(line) / wps <= MAX_BEAT * 1.5:
            beats.append(line)
            continue
        # Long paragraph: break it at sentence ends so the timings mean
        # something, and let the report say it was split.
        parts = [p.strip() for p in SENT_RE.findall(line) if p.strip()]
        buf = ""
        for part in parts:
            candidate = (buf + " " + part).strip()
            if buf and units(candidate) / wps > MAX_BEAT:
                beats.append(buf)
                buf = part
            else:
                buf = candidate
        if buf:
            beats.append(buf)
    return beats


def analyse(raw, wpm=165, target=None, lang="en", sps=5.2):
    units, wps, unit = clock(lang, wpm, sps)
    concrete_re = ES["concrete_re"] if lang == "es" else CONCRETE_RE
    stopwords = ES["stopwords"] if lang == "es" else STOPWORDS
    beats = split_beats(raw, wps, units)
    if not beats:
        return None

    rows, elapsed = [], 0.0
    for i, text in enumerate(beats):
        n = len(words(text, lang))
        dur = units(text) / wps
        rows.append({
            "n": i + 1,
            "start": round(elapsed, 2),
            "dur": round(dur, 2),
            "words": n,
            "text": text,
            "concrete": len(concrete_re.findall(text)),
            "label": "",
            "flags": [],
        })
        if lang == "es":
            rows[-1]["syllables"] = units(text)
        elapsed += dur
    total = elapsed

    # Label the structural positions a Reel is actually built around.
    for r in rows:
        if r["n"] == 1 or r["start"] + r["dur"] <= HOOK_WINDOW:
            r["label"] = "HOOK"
    rows[-1]["label"] = "CTA" if rows[-1]["label"] != "HOOK" else "HOOK/CTA"
    half = total / 2
    for r in rows:
        if not r["label"] and r["start"] <= half < r["start"] + r["dur"]:
            r["label"] = "MID"

    notes = []
    if rows[0]["dur"] > HOOK_WINDOW:
        rows[0]["flags"].append(f"hook runs {rows[0]['dur']:.1f}s, past the {HOOK_WINDOW:.0f}s mark")
        notes.append(f"Beat 1 takes {rows[0]['dur']:.1f}s to say. Cut it to "
                     f"{int(HOOK_WINDOW * wps)} {unit} or fewer, or the hook lands after "
                     "the decision has been made.")
    if rows[0]["concrete"] == 0:
        notes.append("Beat 1 has no number and no name in it. Hooks without something "
                     "checkable are the ones that get scrolled.")

    for r in rows:
        if r["dur"] > MAX_BEAT:
            r["flags"].append(f"{r['dur']:.1f}s on one beat")
    long_beats = [r["n"] for r in rows if r["dur"] > MAX_BEAT]
    if long_beats:
        notes.append(f"Beat(s) {', '.join(map(str, long_beats))} run past {MAX_BEAT:.0f}s. "
                     "Either split the line or change what is on screen inside it. "
                     "A static frame is where people leave.")

    run, start = 0, None
    for r in rows:
        if r["concrete"] == 0:
            run += 1
            start = start if start is not None else r["n"]
            if run == ABSTRACT_RUN:
                notes.append(f"Beats {start}-{r['n']} have nothing concrete in them. "
                             "Put a number, a name or a price in one of them.")
        else:
            run, start = 0, None

    # Does the last line hand you back to the first one?
    first = {w.lower() for w in words(rows[0]["text"], lang) if w.lower() not in stopwords}
    last = {w.lower() for w in words(rows[-1]["text"], lang) if w.lower() not in stopwords}
    loop = sorted(pretty(w, "." if lang == "es" else ",") for w in first & last)
    if loop:
        notes.append(f"Loops: the last beat repeats \"{', '.join(loop[:3])}\" from the hook. "
                     "Second watches are free reach.")
    else:
        notes.append("No loop. The last beat shares no word with the hook, so the video "
                     "ends flat. Echoing one word from beat 1 is the cheapest replay you get.")

    if target:
        delta = total - target
        if abs(delta) <= target * 0.1:
            notes.append(f"Length is on target ({total:.1f}s against {target}s).")
        elif delta > 0:
            notes.append(f"{delta:.1f}s over target. Cut about {int(delta * wps)} {unit}.")
        else:
            notes.append(f"{-delta:.1f}s under target. Either add {int(-delta * wps)} {unit} "
                         "or shoot it short. Short is usually right.")

    result = {
        "wpm": wpm, "target": target,
        "total_seconds": round(total, 2),
        "total_words": sum(r["words"] for r in rows),
        "beats": rows,
        "notes": notes,
    }
    if lang == "es":
        result.update(wpm=None, lang="es", syllables_per_second=sps,
                      total_syllables=sum(r["syllables"] for r in rows))
    return result


def render(a, out=sys.stdout):
    rate = (f"{a['syllables_per_second']} syllables/s" if a.get("lang") == "es"
            else f"{a['wpm']} wpm")
    head = (f"BEAT SHEET  ·  {a['total_words']} words  ·  ~{a['total_seconds']:.1f}s "
            f"at {rate}" + (f"  ·  target {a['target']}s" if a["target"] else ""))
    print("\n" + head, file=out)
    print("=" * max(len(head), 72), file=out)
    for r in a["beats"]:
        label = f"{r['label']:<8}" if r["label"] else " " * 8
        print(f"  {tc(r['start'])}  {r['dur']:4.1f}s  {label}{r['text']}", file=out)
        for f in r["flags"]:
            print(f"  {'':>6}  {'':>5}  {'':<8}^ {f}", file=out)
    print("-" * max(len(head), 72), file=out)
    for n in a["notes"]:
        print(f"  - {n}", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Time a Reel script into a beat sheet.")
    ap.add_argument("input", nargs="?", default="-", help="script file, or - for stdin")
    ap.add_argument("--wpm", type=float, default=165, help="speaking rate (default 165)")
    ap.add_argument("--target", type=float, help="target length in seconds")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lang", default="en", choices=["en", "es"],
                    help="script language (default en; es times by syllables)")
    ap.add_argument("--sps", type=float, default=5.2,
                    help="Spanish speaking rate in syllables per second (default 5.2)")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, wpm=args.wpm, target=args.target, lang=args.lang, sps=args.sps)
    if not a:
        print("empty script", file=sys.stderr)
        sys.exit(2)
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0)


if __name__ == "__main__":
    main()
