"""
syllables.py - count spoken Spanish syllables from spelling.

Spanish spelling is close to phonemic, so syllables can be counted from the
vowels alone: every syllable has exactly one vowel nucleus, and the only
question is whether two vowels next to each other share one.

  strong vowels   a e o (and any accented vowel)
  weak vowels     i u ü (unaccented)

  weak + anything, anything + weak  -> one nucleus (diphthong: "cie-lo", "a-gua")
  strong + strong                   -> two nuclei  (hiatus: "le-er", "ca-os")
  accented weak (í, ú)              -> always its own nucleus ("dí-a", "ba-úl")

The silent u in "que", "qui", "gue", "gui" is weak, so it merges with the
vowel after it and is never counted twice. A final "y" ("hoy", "muy") is a
glide and is ignored; a "y" between consonants ("Python") is a vowel. Numbers are read out as words, so "18.000" counts as
"dieciocho mil".

Why syllables at all: Spanish is spoken faster than English in syllables per
second (7.82 vs 6.19 read aloud, Pellegrino et al. 2011) but carries less
information per syllable, so a word count times a words-per-minute rate is a
poor clock for Spanish. Long words like "implementación" take five syllables
to say, and that is what the viewer waits through.
"""

import re

STRONG = set("aeoáéíóú")
VOWELS = set("aeiouáéíóúü")
WORD_RE = re.compile(r"[^\W\d_]+|\d[\d.,]*|[€$%]")
SYMBOLS = {"€": "euros", "$": "dólares", "%": "por ciento"}   # said, not seen

_UNITS = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
          "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete",
          "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés",
          "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho",
          "veintinueve"]
_TENS = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta",
         "noventa"]
_HUNDREDS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos",
             "seiscientos", "setecientos", "ochocientos", "novecientos"]


def _below_thousand(n):
    if n == 100:
        return "cien"
    h, rest = divmod(n, 100)
    out = [_HUNDREDS[h]] if h else []
    if rest < 30:
        out.append(_UNITS[rest])
    else:
        t, u = divmod(rest, 10)
        out.append(_TENS[t] + (" y " + _UNITS[u] if u else ""))
    return " ".join(w for w in out if w)


def number_to_words(n):
    """Spell a whole number the way it is said: 18000 -> 'dieciocho mil'."""
    if n == 0:
        return "cero"
    parts = []
    millions, n = divmod(n, 1_000_000)
    thousands, n = divmod(n, 1000)
    if millions:
        parts.append("un millón" if millions == 1 else _below_thousand(millions) + " millones")
    if thousands:
        parts.append("mil" if thousands == 1 else _below_thousand(thousands) + " mil")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def count_word(word):
    """Syllables in one Spanish word."""
    w = word.lower()
    if w.endswith("y") and len(w) > 1 and w[-2] in VOWELS:
        w = w[:-1]                       # "hoy", "muy", "rey": the y is a glide
    # A y with no vowel beside it is the vowel itself, as in loanwords
    # ("Python", "byte", "Ryan").
    w = re.sub(r"(?<![aeiouáéíóúü])y(?![aeiouáéíóúü])", "i", w)
    nuclei, prev = 0, None
    for ch in w:
        if ch not in VOWELS:
            prev = None
            continue
        if prev is None:
            nuclei += 1
        elif prev in STRONG and ch in STRONG:
            nuclei += 1                  # hiatus: two strong vowels, two syllables
        prev = ch
    return max(nuclei, 1)


def count(text):
    """Syllables in a line of Spanish, with figures read out as words."""
    total = 0
    for token in WORD_RE.findall(text):
        if token in SYMBOLS:
            total += sum(count_word(w) for w in SYMBOLS[token].split())
        elif token[0].isdigit():
            digits = re.sub(r"[.,](?=\d{3}\b)", "", token)
            whole = re.split(r"[.,]", digits)[0]
            spoken = number_to_words(int(whole)) if whole.isdigit() and len(whole) < 10 else token
            total += sum(count_word(w) for w in spoken.split())
        else:
            total += count_word(token)
    return total
