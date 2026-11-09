"""S1 · Science news outlets (SINC, The Conversation, ScienceDaily): which neuro feeds exist.

Topic IDs of The Conversation found with its search page (the guessed ones were other topics).
"""

import re

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


def main() -> None:
    with client() as c:
        for key, (outlet, lang, url) in CANDIDATES.items():
            print(f"{outlet} [{lang}] {key}")
            r = get(c, url, pause=1.0)
            head = r.text[:600]
            if r.status_code != 200 or not ("<rss" in head or "<feed" in head):
                print("  not a feed")
                continue
            titles = re.findall(r"<title[^>]*>(.*?)</title>", r.text, re.DOTALL)[1:]
            neuro = [t for t in titles if NEURO.search(t)]
            print(f"  {len(titles)} items, {len(neuro)} with a neuro word in the title")
            save_text("news", f"{key}.xml", r.text)


if __name__ == "__main__":
    main()
