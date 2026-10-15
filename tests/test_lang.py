"""
Tests for --lang support. Standard library only:

  python3 -m unittest discover tests

Every test drives the scripts through their command line, the same way the
skills do. The English tests pin the numbers the README prints, so adding a
language cannot quietly move them.
"""

import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")


def run(script, *args, stdin=""):
    proc = subprocess.run([sys.executable, os.path.join(SKILLS, script), *args],
                          input=stdin, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def run_json(script, *args, stdin=""):
    return json.loads(run(script, *args, "--json", stdin=stdin)[1])


EN_HOOKS = "\n".join([
    "Nobody tells you that your first 30 reels are supposed to flop.",
    "I lost $18,000 because of one missing contract.",
    "Stop scrolling if you want to grow on Instagram in 2026 🔥",
    "Hey guys, today I wanted to talk about content strategy",
])

ES_HOOKS = "\n".join([
    "Perdí 18.000 € por un contrato que no firmé.",
    "Si programas con Python y no tienes una app publicada, escucha esto.",
    "Hola chicos, hoy quería hablaros de estrategia de contenido",
    "En este vídeo te voy a enseñar a crear una app",
    "Bueno, vamos a ver cómo se despliega una aplicación",
])


class EnglishUnchanged(unittest.TestCase):
    def test_hookscore_matches_readme(self):
        scores = [h["score"] for h in run_json("ig-reel/hookscore.py", "-", stdin=EN_HOOKS)]
        self.assertEqual(scores, [85.6, 81.4, 54.4, 9.6])

    def test_hookscore_explicit_en_is_default(self):
        default = run("ig-reel/hookscore.py", "-", stdin=EN_HOOKS)
        explicit = run("ig-reel/hookscore.py", "-", "--lang", "en", stdin=EN_HOOKS)
        self.assertEqual(default, explicit)

    def test_beats_keeps_english_word_clock(self):
        script = ("I lost $18,000 because of one missing contract.\n"
                  "Here is the exact clause I now put in every single proposal.\n")
        a = run_json("ig-reel/beats.py", "-", stdin=script)
        self.assertEqual(a["wpm"], 165)
        self.assertNotIn("lang", a)
        # 8 + 12 words at 165 wpm
        self.assertEqual(a["total_words"], 20)
        self.assertAlmostEqual(a["total_seconds"], round(20 / 2.75, 2))


class SpanishHooks(unittest.TestCase):
    def setUp(self):
        out = run_json("ig-reel/hookscore.py", "-", "--lang", "es", stdin=ES_HOOKS)
        self.by_hook = {h["hook"]: h for h in out}

    def test_concrete_spanish_hooks_are_strong(self):
        self.assertEqual(self.by_hook["Perdí 18.000 € por un contrato que no firmé."]["verdict"],
                         "STRONG")

    def test_greeting_is_a_dealbreaker(self):
        h = self.by_hook["Hola chicos, hoy quería hablaros de estrategia de contenido"]
        self.assertEqual(h["verdict"], "WEAK")
        self.assertTrue(any("Greeting" in f for f in h["flags"]))

    def test_video_preamble_is_a_dealbreaker(self):
        h = self.by_hook["En este vídeo te voy a enseñar a crear una app"]
        self.assertTrue(any("preamble" in f for f in h["flags"]))

    def test_filler_opener_loses_frontload(self):
        h = self.by_hook["Bueno, vamos a ver cómo se despliega una aplicación"]
        self.assertIn("weak opener", h["checks"]["FRONTLOAD"]["detail"])

    def test_second_person_verb_counts_as_addressing_the_viewer(self):
        h = self.by_hook["Si programas con Python y no tienes una app publicada, escucha esto."]
        self.assertEqual(h["checks"]["ADDRESS"]["score"], 100.0)

    def test_euro_figure_is_one_concrete_marker(self):
        h = self.by_hook["Perdí 18.000 € por un contrato que no firmé."]
        self.assertIn("18.000 €", h["checks"]["SPECIFICITY"]["detail"])

    def test_accented_words_are_not_split(self):
        out = run_json("ig-reel/hookscore.py", "--hook", "Programación en dos semanas",
                       "--lang", "es")
        self.assertTrue(out["checks"]["LENGTH"]["detail"].startswith("4 words"))


class SpanishBeats(unittest.TestCase):
    def test_times_by_syllables(self):
        a = run_json("ig-reel/beats.py", "-", "--lang", "es", "--sps", "5",
                     stdin="Perdí dieciocho mil euros.\n")
        # per-dí die-cio-cho mil eu-ros = 2 + 3 + 1 + 2 = 8 syllables, 1.6 s at 5/s
        self.assertEqual(a["total_syllables"], 8)
        self.assertAlmostEqual(a["total_seconds"], 1.6)

    def test_figures_and_symbols_are_read_out(self):
        a = run_json("ig-reel/beats.py", "-", "--lang", "es",
                     stdin="Perdí 18.000 €.\n")
        b = run_json("ig-reel/beats.py", "-", "--lang", "es",
                     stdin="Perdí dieciocho mil euros.\n")
        self.assertEqual(a["total_syllables"], b["total_syllables"])

    def test_loop_shows_spanish_thousands(self):
        a = run_json("ig-reel/beats.py", "-", "--lang", "es",
                     stdin="Perdí 18.000 € por un contrato.\nNo pierdas 18.000 € como yo.\n")
        self.assertTrue(any('"18.000"' in n for n in a["notes"]))


class SpanishCaption(unittest.TestCase):
    CAPTION = ("Perdí 18.000 € por una cláusula.\n\n"
               "Comenta GUIA y te mando los 5 pasos.\n\n"
               "#programación #python #parati")

    def test_keyword_ask_and_accented_tags(self):
        a = run_json("ig-caption/caption.py", "-", "--lang", "es", stdin=self.CAPTION)
        self.assertEqual(a["asks"], ["comment a keyword"])
        self.assertIn("#programación", a["hashtags"])

    def test_spanish_filler_tag_is_flagged(self):
        a = run_json("ig-caption/caption.py", "-", "--lang", "es", stdin=self.CAPTION)
        tags = next(c for c in a["checks"] if c["check"] == "HASHTAGS")
        self.assertIn("#parati", tags["detail"])


class SpanishHumanizer(unittest.TestCase):
    PUNCTUATION = ("—¿Vienes? —preguntó Ana.\n"
                   "Mi madre ―que no sabe de móviles― lo usa a diario.\n"
                   "Dijo «ya está» y se fue.\n")
    AI = ("En el mundo actual, es fundamental sumergirse en el apasionante universo "
          "de la programación — un verdadero antes y un después. Además, cabe destacar "
          "que esta herramienta revolucionaria te permite potenciar tu productividad.\n")
    HUMAN = ("Si programas con Python, esto te interesa. Yo tardé 3 meses en sacar mi "
             "primera app. Lo jodido viene después: desplegarla en un servidor que no se "
             "caiga cada dos días. ¿Por qué? Porque nadie te lo explica. Nada más. Xauu\n")

    def test_correct_spanish_punctuation_is_untouched(self):
        _, out, _ = run("ig-human/humanize.py", "-", "--lang", "es", stdin=self.PUNCTUATION)
        self.assertEqual(out, self.PUNCTUATION)

    def test_spaced_em_dash_and_slop_are_removed(self):
        _, out, _ = run("ig-human/humanize.py", "-", "--lang", "es", stdin=self.AI)
        self.assertNotIn("—", out)
        for slop in ("En el mundo actual", "cabe destacar", "revolucionaria", "potenciar"):
            self.assertNotIn(slop, out)
        self.assertIn("programación", out)

    def test_human_voice_scores_above_ai_voice(self):
        ai = run_json("ig-human/detect.py", "-", "--lang", "es", stdin=self.AI)
        human = run_json("ig-human/detect.py", "-", "--lang", "es", stdin=self.HUMAN)
        self.assertGreater(human["human_score"], ai["human_score"])

    def test_dialogue_raya_is_not_a_fingerprint(self):
        out = run_json("ig-human/detect.py", "-", "--lang", "es", stdin=self.PUNCTUATION)
        self.assertIn("0 em dash", out["checks"]["FINGERPRINT"]["detail"])


class SpanishHookFormulas(unittest.TestCase):
    def test_same_ids_as_english(self):
        with open(os.path.join(SKILLS, "ig-reel", "hooks.json"), encoding="utf-8") as fh:
            en = json.load(fh)
        with open(os.path.join(SKILLS, "ig-reel", "hooks.es.json"), encoding="utf-8") as fh:
            es = json.load(fh)
        self.assertEqual([h["id"] for h in es["hooks"]], [h["id"] for h in en["hooks"]])
        self.assertEqual(es["classify_order"], en["classify_order"])

    def test_every_example_classifies_to_its_own_formula(self):
        import re
        with open(os.path.join(SKILLS, "ig-reel", "hooks.es.json"), encoding="utf-8") as fh:
            es = json.load(fh)
        by_id = {h["id"]: h for h in es["hooks"]}
        for h in es["hooks"]:
            first = next(i for i in es["classify_order"]
                         if re.search(by_id[i]["match"], h["example"], re.IGNORECASE))
            self.assertEqual(first, h["id"], h["example"])

    def test_swipe_names_spanish_formulas(self):
        tsv = ("account\tfollowers\tmedian\tviews\thook\n"
               "@a\t50000\t10000\t400000\tNadie te cuenta que saber Python no basta\n"
               "@b\t20000\t5000\t6000\tHola chicos, en este vídeo os enseño a programar\n")
        code, out, _ = run("ig-viral/swipe.py", "-", "--lang", "es", stdin=tsv)
        self.assertEqual(code, 0)
        self.assertIn("Lo que nadie te cuenta", out)


if __name__ == "__main__":
    unittest.main()
