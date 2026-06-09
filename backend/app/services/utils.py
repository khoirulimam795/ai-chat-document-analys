import re
import hashlib

SLANG_DICT = {
    # Singkatan umum
    "gws": "gak guna sia sia",
    "baper": "bawa perasaan",
    "gabut": "gak ada kegiatan",
    "bgt": "banget",
    "anjay": "wow keren",
    "anjir": "wow",
    "wkwk": "ketawa",
    "wkwkwk": "ketawa",
    "btw": "by the way",
    "imo": "in my opinion",
    "imho": "in my humble opinion",
    "lol": "laugh out loud",
    "omg": "oh my god",
    "pls": "please",
    "plis": "please",
    "dll": "dan lain lain",
    "dsb": "dan sebagainya",
    "dkk": "dan kawan kawan",
    # Kata gaul
    "kepo": "ingin tahu",
    "mager": "malas gerak",
    "gercep": "gerak cepat",
    "gabisa": "tidak bisa",
    "gakbisa": "tidak bisa",
    "gk": "tidak",
    "gak": "tidak",
    "nggak": "tidak",
    "enggak": "tidak",
    "iy": "iya",
    "iyh": "iya",
    "yah": "ya",
    "bolehj": "boleh juga",
    "mksd": "maksud",
    "tny": "tanya",
    "jwb": "jawab",
    "gw": "saya",
    "gua":"saya",
    "lu":"anda",
    "lo":"anda"
}

def normalize_slang(text: str) -> str:
    words = text.split()
    normalized = []
    for word in words:
        clean = re.sub(r'[^\w]', '', word.lower())
        normalized.append(SLANG_DICT.get(clean, word))
    return " ".join(normalized)

def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    return text.strip()