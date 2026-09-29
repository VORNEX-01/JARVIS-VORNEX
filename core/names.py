"""core/names.py - match a name the way a person would.

The task says "ماهک"; the screen says "Mahak". They are the same person. Exact
string equality fails; letter-by-letter comparison fails; so we compare SOUND:
fold the script, transliterate Persian/Arabic to Latin, drop the vowels, and
compare skeletons. If two candidates are equally close we return None - the
caller must ask, never guess.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

_ZWNJ = "\u200c\u200d\u200e\u200f"
_FOLD = str.maketrans({
    "ي": "ی", "ك": "ک", "ى": "ی", "ﻯ": "ی", "ﻰ": "ی", "ۀ": "ه", "ة": "ه",
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ؤ": "و", "ئ": "ی",
})
_DIAC = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_NONWORD = re.compile(r"[^\w\u0600-\u06FF]+", re.UNICODE)

_TR = {
    "ا": "a", "آ": "a", "أ": "a", "إ": "a", "ب": "b", "پ": "p", "ت": "t",
    "ث": "s", "ج": "j", "چ": "ch", "ح": "h", "خ": "kh", "د": "d", "ذ": "z",
    "ر": "r", "ز": "z", "ژ": "zh", "س": "s", "ش": "sh", "ص": "s", "ض": "z",
    "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "gh", "ک": "k",
    "ك": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n", "و": "v", "ه": "h",
    "ی": "y", "ي": "y", "ء": "", "ة": "h", "ؤ": "o", "ئ": "y",
}
_VOWELS = set("aeiou")


def norm(s) -> str:
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = s.translate(_FOLD)
    s = _DIAC.sub("", s)
    s = "".join(ch for ch in s if ch not in _ZWNJ)
    s = _NONWORD.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


def _is_ara(s: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in s)


def translit(s) -> str:
    out = []
    for ch in str(s or ""):
        if ch in _TR:
            out.append(_TR[ch])
        elif ch.isascii() and ch.isalnum():
            out.append(ch)
    return "".join(out)


def skeleton(s) -> str:
    """Consonant skeleton: ماهک -> mahk -> mhk, Mahak -> mhk."""
    n = translit(s) if _is_ara(str(s or "")) else norm(s)
    n = re.sub(r"[^a-z]", "", n)
    return "".join(c for c in n if c not in _VOWELS)




def best(query, cands, key=None, floor=0.72, margin=0.06):
    """The single best candidate, or None when the answer is not clear."""
    scored = []
    for c in cands:
        v = c.get(key) if (key and isinstance(c, dict)) else c
        scored.append((score(query, v), c))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    top, val = scored[0]
    if top < floor:
        return None
    second = scored[1][0] if len(scored) > 1 else 0.0
    if top - second < margin and second >= floor:
        return None          # two equally likely people: never guess
    return val


# ── score the NAME, not the whole row (appended last: this wins) ─────────────
# A chat row is "Name, preview, time". Comparing the whole row against a name
# gave every row that merely CONTAINED those letters the same 0.90, so three
# different chats tied and we refused to choose. Containment now loses points for
# every extra letter, and `lead` gives the part that is actually the name.

def lead(s, maxlen=60):
    t = str(s or "").strip()
    t = re.split(r"[,،|·•\u2013\u2014:\n]", t, 1)[0].strip()
    return (t or str(s or "").strip())[:maxlen]




# ── name matching v2: Persian vowels are optional, Latin vowels are a control ─
# MEASURED: علی/Ali 0.67, حسین/Hossein 0.75, امیر/نیما/سینا 0.80 - all below the
# 0.85 gate, because translit maps ی->y, و->v so Persian keeps them as consonants
# while the Latin romanisation reshapes them (and doubles letters: Hossein). The
# bare consonant skeleton is also too loose: Sara/Sora and Ali/Oli collapse to the
# SAME skeleton, and the old fallback (ratio on skeletons) even returned 1.0 for
# them. So consonants decide, and for SHORT skeletons the vowels act as a control:
# Persian omits short vowels, so its vowels must be a SUBSET of the Latin ones,
# while two Latin strings must agree on their vowels.

def _phonstr(s):
    n = translit(s) if _is_ara(str(s or "")) else norm(s)
    n = re.sub(r"[^a-z]", "", n.lower())
    n = n.replace("y", "i").replace("w", "u")      # ی/و behave as vowels in Latin
    out = []
    for c in n:                                     # collapse doubles: ss -> s
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


def _phon(s):
    n = _phonstr(s)
    return ("".join(c for c in n if c not in "aeiou"),
            "".join(c for c in n if c in "aeiou"))


def score(a, b):
    """0..1 similarity of two names, robust across Persian<->Latin spelling."""
    sa, sb = str(a or ""), str(b or "")
    na, nb = norm(sa), norm(sb)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    ca, va = _phon(sa)
    cb, vb = _phon(sb)

    if ca and ca == cb:
        if len(ca) >= 3:
            return 0.97
        if va and vb:
            if va == vb:
                return 0.93
            if _is_ara(sa) != _is_ara(sb) and (set(va) <= set(vb) or set(vb) <= set(va)):
                return 0.92
    if len(ca) >= 3 and len(cb) >= 3 and (ca in cb or cb in ca):
        return max(0.86, 0.92 - 0.05 * abs(len(cb) - len(ca)))

    pa, pb = _phonstr(sa), _phonstr(sb)
    r1 = difflib.SequenceMatcher(None, na, nb).ratio()
    r2 = difflib.SequenceMatcher(None, pa, pb).ratio()      # NEVER the bare skeleton
    r3 = 0.85 if ((na in nb or nb in na)
                  and abs(len(na) - len(nb)) <= max(3, len(na) // 2)) else 0.0
    return max(r1, r2, r3)
