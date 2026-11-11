"""S1 · Science news outlets (SINC, The Conversation, ScienceDaily): which neuro feeds exist.

Topic IDs of The Conversation found with its search page (the guessed ones were other topics).
"""

import re
import sys

from common import client, get, save_text

# feed key: (outlet, lang, url)
CANDIDATES = {
    "sciencedaily_neuroscience": (
        "ScienceDaily", "en", "https://www.sciencedaily.com/rss/mind_brain/neuroscience.xml"),
    "conversation_neuroscience": (
        "The Conversation", "en", "https://theconversation.com/topics/neuroscience-427/articles.atom"),
    "conversation_es_neurociencia": (
        "The Conversation", "es", "https://theconversation.com/es/topics/neurociencia-55189/articles.atom"),
    "conversation_es_cerebro": (
        "The Conversation", "es", "https://theconversation.com/es/topics/cerebro-54660/articles.atom"),
    "sinc_salud": ("SINC", "es", "https://www.agenciasinc.es/feed/Salud"),
    "sinc_noticias": ("SINC", "es", "https://www.agenciasinc.es/feed/Noticias"),
}  # fmt: skip

NEURO = re.compile(r"neur|brain|cerebr|alzh|parkinson|epilep|dement|memori|memory", re.I)
MAX_ITEMS = 12  # SINC sends 150 items (~3 MB): keep a few, with some neuro ones


def trim_items(text: str, keep: int = MAX_ITEMS) -> str:
    """Keep the first items plus neuro ones, up to `keep`, in feed order."""
    items = re.findall(r"\s*<item>.*?</item>", text, re.DOTALL)
    if len(items) <= keep:
        return text
    neuro = [i for i in items if NEURO.search(re.search(r"<title>(.*?)</title>", i, re.S)[1])]
    chosen = set(neuro[: keep // 2])
    chosen |= set([i for i in items if i not in chosen][: keep - len(chosen)])
    start, end = text.index(items[0]), text.index(items[-1]) + len(items[-1])
    return text[:start] + "".join(i for i in items if i in chosen) + text[end:]


def main() -> None:
    only = sys.argv[1:]  # optional key prefixes, e.g. `sinc`
    with client() as c:
        for key, (outlet, lang, url) in CANDIDATES.items():
            if only and not key.startswith(tuple(only)):
                continue
            print(f"{outlet} [{lang}] {key}")
            r = get(c, url, pause=1.0)
            head = r.text[:600]
            if r.status_code != 200 or not ("<rss" in head or "<feed" in head):
                print("  not a feed")
                continue
            titles = re.findall(r"<title[^>]*>(.*?)</title>", r.text, re.DOTALL)[1:]
            neuro = [t for t in titles if NEURO.search(t)]
            print(f"  {len(titles)} items, {len(neuro)} with a neuro word in the title")
            save_text("news", f"{key}.xml", trim_items(r.text))


if __name__ == "__main__":
    main()
