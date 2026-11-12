"""Checks for the static site, run from the repository root with pytest.

The checks against the apps read ../BananaWiki (or BANANAWIKI_SRC) and
../BananaChat (or BANANACHAT_SRC) and are skipped when those are missing.
SITE_ROOT checks another copy of the site.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(os.environ.get("SITE_ROOT") or Path(__file__).resolve().parents[1])
SUITE = ROOT.parent
WIKI_SRC = Path(os.environ.get("BANANAWIKI_SRC") or SUITE / "BananaWiki")
CHAT_SRC = Path(os.environ.get("BANANACHAT_SRC") or SUITE / "BananaChat")
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "wbr"}
CSP = ("default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; "
       "form-action 'none'; object-src 'none'")
LANGS = ("en", "it", "de")
FOOTER = {"en": "Maintained by Luca Zani and contributors.", "it": "Mantenuta da Luca Zani e collaboratori.",
          "de": "Gepflegt von Luca Zani und Mitwirkenden."}
ABOUT = ("about/index.html", "about/index.it.html", "about/index.de.html")
STARTED = {"en": "Luca Zani started BananaWiki on 20 February 2026",
           "it": "Luca Zani ha avviato BananaWiki il 20 febbraio 2026",
           "de": "Luca Zani startete BananaWiki am 20. Februar 2026"}


class Page(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.path = path
        self.rel = path.relative_to(ROOT).as_posix()
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.ids: list[str] = []
        self.links: list[str] = []
        self.images: list[dict[str, str]] = []
        self.alternates: dict[str, str] = {}
        self.meta: dict[str, str] = {}
        self.lang = ""
        self.text: list[str] = []
        self.rows: list[tuple[str, list[str]]] = []
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self.feed(path.read_text(encoding="utf-8"))
        self.close()
        if self.stack:
            self.errors.append(f"unclosed {self.stack}")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {key: value or "" for key, value in attrs}
        if tag == "html":
            self.lang = a.get("lang", "")
        if "id" in a:
            if a["id"] in self.ids:
                self.errors.append(f"duplicate id {a['id']}")
            self.ids.append(a["id"])
        if "style" in a:
            self.errors.append(f"inline style on <{tag}> (blocked by the CSP)")
        self.links += [a[key] for key in ("href", "src") if key in a]
        if tag == "img":
            self.images.append(a)
        if tag == "link" and a.get("rel") == "alternate":
            self.alternates[a.get("hreflang", "")] = a.get("href", "")
        if tag == "meta" and "http-equiv" in a:
            self.meta[a["http-equiv"]] = a.get("content", "")
        if tag == "tr":
            self._row = []
        if tag in ("th", "td") and self._row is not None:
            self._cell = []
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"</{tag}> at line {self.getpos()[0]} does not close <{self.stack[-1:]}>")
            if tag in self.stack:
                del self.stack[len(self.stack) - 1 - self.stack[::-1].index(tag):]
            return
        self.stack.pop()
        if tag in ("th", "td") and self._cell is not None and self._row is not None:
            self._row.append(_clean("".join(self._cell)))
            self._cell = None
        if tag == "tr" and self._row:
            self.rows.append((self._row[0], self._row[1:]))
            self._row = None

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._cell is not None:
            self._cell.append(data)

    @property
    def content(self) -> str:
        return _clean(" ".join(self.text))

    def table(self) -> dict[str, list[str]]:
        return dict(self.rows)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


PAGES = {
    path.relative_to(ROOT).as_posix(): path
    for path in sorted(ROOT.rglob("*.html"))
    if not {".git", "tests"} & set(path.relative_to(ROOT).parts)
}


@pytest.fixture(scope="module")
def pages() -> dict[str, Page]:
    return {rel: Page(path) for rel, path in PAGES.items()}


def _target(rel: str, link: str) -> tuple[str, str]:
    """The page (relative to ROOT) and fragment a local link points to."""
    parts = urlsplit(link)
    path = unquote(parts.path)
    if not path:
        return rel, parts.fragment
    target = os.path.normpath(os.path.join(os.path.dirname(rel), path))
    if path.endswith("/") or (ROOT / target).is_dir():
        target = os.path.join(target, "index.html")
    return Path(target).as_posix(), parts.fragment


def _local(link: str) -> bool:
    return not urlsplit(link).scheme and not link.startswith("//")


def _version(rel: str, lang: str) -> str:
    """The page in another language: index.html, index.it.html and index.de.html are one page."""
    base = re.sub(r"\.(?:it|de)\.html$", ".html", rel)
    return base if lang == "en" else base.replace(".html", f".{lang}.html")


HOMES = {lang: (_version("index.html", lang), _version("unavailable.html", lang)) for lang in LANGS}


def test_the_site_has_six_pages_in_three_languages():
    assert len(PAGES) == 18, sorted(PAGES)
    assert {_version(rel, lang) for rel in PAGES for lang in LANGS} == set(PAGES)


@pytest.mark.parametrize("rel", sorted(PAGES))
def test_page_structure(pages, rel):
    page = pages[rel]
    assert page.errors == []
    assert page.lang in LANGS
    assert rel == _version(rel, page.lang), f"{rel} is not named for its language"
    assert page.meta.get("Content-Security-Policy") == CSP
    assert "content" in page.ids, "the skip link needs #content"


def test_local_links_and_fragments_resolve(pages):
    broken = []
    for rel, page in pages.items():
        for link in filter(_local, page.links):
            target, fragment = _target(rel, link)
            if not (ROOT / target).is_file():
                broken.append(f"{rel}: {link}")
            elif fragment and target in pages and fragment not in pages[target].ids:
                broken.append(f"{rel}: {link} (no #{fragment})")
    assert broken == []


def test_asset_versions_match_their_content(pages):
    stale = []
    for rel, page in pages.items():
        for link in filter(_local, page.links):
            parts = urlsplit(link)
            version = dict(item.split("=", 1) for item in parts.query.split("&") if "=" in item).get("v")
            if version is None:
                continue
            target, _ = _target(rel, parts.path)
            digest = hashlib.sha256((ROOT / target).read_bytes()).hexdigest()[:12]
            if version != digest:
                stale.append(f"{rel}: {link} (content is {digest})")
    assert stale == []


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", f"{path.name} is not a PNG"
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def test_images_state_their_real_size(pages):
    """Recaptured screenshots change height; stale width/height attributes distort the reserved space."""
    wrong = []
    for rel, page in pages.items():
        for image in page.images:
            target, _ = _target(rel, urlsplit(image["src"]).path)
            assert image.get("alt") is not None, f"{rel}: {image['src']} has no alt attribute"
            size = _png_size(ROOT / target)
            if (image.get("width"), image.get("height")) != tuple(map(str, size)):
                wrong.append(f"{rel}: {image['src']} says {image.get('width')}x{image.get('height')}, "
                             f"the file is {size[0]}x{size[1]}")
    assert wrong == []


def test_every_published_image_is_used(pages):
    """Screenshots of removed features are deleted rather than left behind in img/."""
    used = {_target(rel, urlsplit(link).path)[0] for rel, page in pages.items() for link in filter(_local, page.links)}
    unused = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "img").iterdir()
                    if path.relative_to(ROOT).as_posix() not in used)
    assert unused == []


def _css_rules(selector: str, sheet: str = "style.css") -> list[str]:
    css = re.sub(r"/\*.*?\*/", "", (ROOT / sheet).read_text(encoding="utf-8"), flags=re.DOTALL)
    return [body for head, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
            if selector in [part.strip() for part in head.split(",")]]


def test_hero_captions_sit_on_the_yellow_band():
    """The band turns yellow behind the lower part of the hero screenshot, so the caption under it and the facts
    after it are dark text on yellow however many lines they wrap to. The caption paints the yellow itself too,
    for contrast checkers, and the screenshot paints above the band."""
    (band,) = _css_rules(".band")
    assert re.search(r"background: linear-gradient\(var\(--color-bg\) calc\(var\(--image-height\) \* \.\d+\), "
                     r"var\(--color-band\) 0\);", band)
    assert "color: var(--color-on-band);" in band and "* .625);" in band, "--image-height assumes 1280x800"
    (caption,) = _css_rules(".hero-figure figcaption")
    assert "background: var(--color-band);" in caption and "color: var(--color-on-band);" in caption
    assert any("position: relative" in rule and "z-index: 1" in rule for rule in _css_rules(".hero-figure-link")), \
        "the screenshot must paint above the band"
    assert any("outline-offset: -" in rule for rule in _css_rules(".hero-figure-link:focus-visible")), \
        "an outside focus ring would vanish against the band"
    heroes = {rel: "img/wiki-home.png" for lang in LANGS for rel in HOMES[lang]}
    heroes.update({_version("bananachat/index.html", lang): "img/bananachat.png" for lang in LANGS})
    for rel, image in heroes.items():
        html = PAGES[rel].read_text(encoding="utf-8")
        band = html.split('<div class="band">', 1)[1].split("</dl>", 1)[0]
        figure = band.split('<figure class="hero-figure">', 1)[1].split("</figure>", 1)[0]
        assert image in figure and "<figcaption>" in figure and '<dl class="facts">' in band, rel
    for image in set(heroes.values()):
        width, height = _png_size(ROOT / image)
        assert width * 10 == height * 16, f"{image} is not 16:10, the shape the band expects"


def _as_published(rel: str) -> str:
    """unavailable*.html replace index*.html when published, and link as them."""
    return rel.replace("unavailable", "index") if "/" not in rel else rel


def test_language_versions_link_to_each_other(pages):
    """Each page names its other two language versions as alternates and links to them in the header."""
    for rel, page in pages.items():
        assert sorted(page.alternates) == sorted(set(LANGS) - {page.lang}), rel
        for other, href in page.alternates.items():
            assert page.links.count(href) >= 2, f"{rel} has no visible link to its {other} version"
            target, _ = _target(rel, href)
            if rel.startswith("unavailable"):
                target = target.replace("index", "unavailable")
            assert target == _version(rel, other), (rel, href)
            assert pages[target].lang == other
            back, _ = _target(target, pages[target].alternates[page.lang])
            assert back == _as_published(rel)


def test_pages_link_to_pages_in_their_own_language(pages):
    for rel, page in pages.items():
        versions = {_target(rel, href)[0] for href in page.alternates.values()}
        for link in filter(_local, page.links):
            target, _ = _target(rel, link)
            if target.endswith(".html") and target in pages and target not in versions:
                assert pages[target].lang == page.lang, f"{rel} links to the {pages[target].lang} page {link}"


def _visible_prose(path: Path) -> str:
    html = re.sub(r"<(pre|code|style|script)\b.*?</\1>", " ", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return _clean(re.sub(r"<[^>]+>", " ", re.sub(r"<head>.*?</head>", " ", html, flags=re.DOTALL)))


@pytest.mark.parametrize("rel", sorted(PAGES))
def test_prose_uses_typographic_apostrophes(rel):
    assert re.findall(r"\w{0,20}\w'\w\w{0,20}", _visible_prose(PAGES[rel])) == []


def test_italian_pages_treat_wiki_as_feminine(pages):
    """The Italian pages say "la wiki", never "il wiki"."""
    masculine = re.compile(r"\b(?:il|un|del|al|dal|nel|sul|questo|quel|tuo|suo|ogni singolo|un solo) wiki\b", re.IGNORECASE)
    found = {rel: masculine.findall(page.content) for rel, page in pages.items() if page.lang == "it"}
    assert {rel: hits for rel, hits in found.items() if hits} == {}


def test_german_pages_treat_wiki_as_neuter(pages):
    """The German pages say "das Wiki", as BananaWiki's German interface does."""
    other = re.compile(r"\b(?:die|der|eine|einer|keine|meine|deine|seine|ihre|unsere|diese|dieser|jede|jeder) "
                       r"Wiki(?![-\w])", re.IGNORECASE)
    found = {rel: other.findall(page.content) for rel, page in pages.items() if page.lang == "de"}
    assert {rel: hits for rel, hits in found.items() if hits} == {}


def _catalogue(root: Path, *parts: str, lang: str | None = None) -> dict[str, str]:
    path = root.joinpath(*parts)
    if not path.is_file():
        pytest.skip(f"{path} is not next to the site")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data[lang] if lang else data


def test_pages_name_each_app_s_controls_as_the_app_does(pages):
    """The pages use each app's own words: Appearance in both apps' account menus (Aspetto, Darstellung), the
    page builder's name, and cards rather than tickets on the kanban ("schede", "Karten")."""
    wiki = {lang: _catalogue(WIKI_SRC, "bananawiki", "wiki", "translations", f"{lang}.json") for lang in LANGS}
    chat = {lang: _catalogue(CHAT_SRC, "bananachat", "i18n", "core.json", lang=lang) for lang in LANGS}
    in_menu = {"en": "under {} in the account menu", "it": "dal menu dell’account, alla voce {}",
               "de": "im Kontomenü unter {}"}
    for rel, page in pages.items():
        if rel in HOMES[page.lang]:
            assert in_menu[page.lang].format(wiki[page.lang]["nav.customize"]) in page.content, rel
        if rel.startswith("bananachat/"):
            assert in_menu[page.lang].format(chat[page.lang]["nav.customize"]) in page.content, rel
        if page.lang == "it":
            assert "costruttore di pagine" not in page.content and "ticket" not in page.content, rel
        if page.lang == "de":
            assert "Ticket" not in page.content, rel
    for lang in ("it", "de"):
        builder = _catalogue(WIKI_SRC, "bananawiki", "wiki", "features", "page_builder", "translations", f"{lang}.json")
        assert builder["feature.page_builder.name"].lower() in pages[HOMES[lang][0]].content.lower(), lang


# Each built-in interface language of the wiki as the site's pages name it.
LANGUAGE_NAMES = {"en": {"de": "German", "en": "English", "it": "Italian"},
                  "it": {"de": "tedesco", "en": "inglese", "it": "italiano"},
                  "de": {"de": "Deutsch", "en": "Englisch", "it": "Italienisch"}}


def _wiki_builtin_languages() -> set[str]:
    """The codes of ``BUILTIN_LANGUAGES`` in the wiki's i18n module, read as data, never imported."""
    path = WIKI_SRC / "bananawiki" / "wiki" / "i18n.py"
    if not path.is_file():
        pytest.skip(f"{path} is not next to the site")
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        if any(isinstance(target, ast.Name) and target.id == "BUILTIN_LANGUAGES" for target in targets):
            return set(ast.literal_eval(node.value))
    pytest.fail(f"{path} does not define BUILTIN_LANGUAGES")


def test_pages_list_the_wiki_s_built_in_interface_languages(pages):
    """The home pages (and their "unavailable" copies) name exactly the languages BananaWiki ships its
    interface in, in the facts band and in "Running the wiki". BananaChat's pages describe its own."""
    codes = _wiki_builtin_languages()
    claims = {"en": (r"<dt>Interface</dt><dd>([^<]*)</dd>", r"<li>Interface in ([^;<]*?)(?:;|, and you can upload)"),
              "it": (r"<dt>Interfaccia</dt><dd>([^<]*)</dd>", r"<li>Interfaccia in ([^;<]*?)(?:;|, e puoi caricare)"),
              "de": (r"<dt>Oberfläche</dt><dd>([^<]*)</dd>", r"<li>Oberfläche auf ([^;<]*?)(?:;|, und du kannst)")}
    for rel in (rel for lang in LANGS for rel in HOMES[lang]):
        lang = pages[rel].lang
        names = LANGUAGE_NAMES[lang]
        assert codes <= names.keys(), f"add the site's name for {sorted(codes - names.keys())} to LANGUAGE_NAMES"
        html = PAGES[rel].read_text(encoding="utf-8")
        for claim in claims[lang]:
            listed = re.findall(claim, html)
            assert len(listed) == 1, (rel, claim)
            said = {name.strip().lower() for name in re.split(r",|\band\b|\be\b|\bund\b", listed[0]) if name.strip()}
            assert said == {names[code].lower() for code in codes}, (rel, listed[0])


def test_english_prose_uses_british_spelling(pages):
    """Both apps' English interfaces write colour, organise, labelled, Customise, enrolment, catalogue and
    licence (the noun); so does the site, in its text, titles and image descriptions."""
    american = re.compile(r"\b(?:colors?|organiz\w*|labeled|centers?|favorite\w*|behaviors?|canceled|customiz\w*"
                          r"|enroll|enrollments?|catalogs?)\b", re.IGNORECASE)
    license_noun = re.compile(r"(?<!Public )\bLicense\b|\blicense\b")  # "licensed" and the AGPL's name are fine
    for rel, page in pages.items():
        if page.lang != "en":
            continue
        html = PAGES[rel].read_text(encoding="utf-8").replace('<meta name="color-scheme" content="dark">', "")
        html = re.sub(r"<(pre|code|style|script)\b.*?</\1>", " ", html, flags=re.DOTALL)
        described = re.findall(r'(?:alt|aria-label|title|content)="([^"]*)"', html)
        text = " ".join([_clean(re.sub(r"<[^>]+>", " ", html)), *described])
        assert american.findall(text) + license_noun.findall(text) == [], rel


# ── Attribution ──────────────────────────────────────────────────────────────


def _site_files() -> list[Path]:
    """Every file of this checkout outside Git's metadata, published or not."""
    skipped = {".git", ".ruff_cache", "__pycache__"}
    return sorted(path for path in ROOT.rglob("*")
                  if path.is_file() and not skipped & set(path.relative_to(ROOT).parts))


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[a-z]{2,}")


def test_every_email_address_is_marked_email_off(pages):
    """CDN email obfuscation turns addresses into links that only work with its own script; it skips text
    inside these markers."""
    loose = []
    for rel, page in pages.items():
        content = page.path.read_text(encoding="utf-8")
        for match in EMAIL.finditer(content):
            before = content[:match.start()]
            if before.rfind("<!--email_off-->") <= before.rfind("<!--/email_off-->"):
                loose.append(f"{rel}: {match.group()}")
    assert loose == []
    assert any("mailto:contact@bananawiki.com" in page.path.read_text(encoding="utf-8") for page in pages.values()), \
        "nothing was checked"


def _origin(pages) -> str:
    """The organisation the English about page says BananaWiki started at."""
    match = re.search(re.escape(STARTED["en"]) + r" at ([^,.;]+)", pages["about/index.html"].content)
    assert match, "the about page says where the project started"
    return match.group(1).strip()


def test_only_the_about_pages_name_where_the_project_started(pages):
    """No other file of this checkout names it; the rest credit "Luca Zani and contributors"."""
    origin = _origin(pages)
    assert all(origin in pages[rel].content for rel in ABOUT)
    name = origin.split()[0].lower().encode()
    others = [path for path in _site_files() if path.relative_to(ROOT).as_posix() not in ABOUT]
    assert ROOT / "README.md" in others, "nothing was checked"
    assert [path.relative_to(ROOT).as_posix() for path in others if name in path.read_bytes().lower()] == []


def test_pages_tell_the_same_story(pages):
    """The home pages tell the short story and send readers to the about page for the rest."""
    for lang in LANGS:
        for rel in (*HOMES[lang], _version("about/index.html", lang)):
            assert STARTED[lang] in pages[rel].content, rel
        for rel in HOMES[lang]:
            html = PAGES[rel].read_text(encoding="utf-8")
            story = html.split("<!-- shared:story -->")[1].split("<!-- /shared:story")[0]
            about = "about/" if lang == "en" else f"about/index.{lang}.html"
            assert f'href="{about}"' in story, f"{rel}: the story links to the about page"
    for rel, page in pages.items():
        assert FOOTER[page.lang] in page.content, rel


# The header's mascot: its labels in each language, as BananaWiki's portal and BananaChat word them for their
# own name (label, label with sunglasses, sunglasses on, sunglasses off).
MASCOT_LABELS = {"en": ("{} mascot", "{} mascot, with sunglasses", "Deal with it.", "Sunglasses off."),
                 "it": ("Mascotte di {}", "Mascotte di {}, con gli occhiali da sole", "Deal with it.", "Occhiali tolti."),
                 "de": ("{}-Maskottchen", "{}-Maskottchen mit Sonnenbrille", "Deal with it.", "Sonnenbrille abgenommen.")}
MASCOT_FILES = ("mascot/mascot.css", "mascot/mascot.js")
BRAND = re.compile(r'<header class="site-header">\s*<div class="container">\s*<div class="brand">\s*'
                   r'<button type="button" class="mascot" ([^>]*)><span class="mascot__body">(<svg [^>]*>.*?</svg>)'
                   r'</span></button>\s*<a class="brand-name" href="([^"]+)">(\w+)</a>\s*</div>', re.DOTALL)


def _mascot(rel: str) -> tuple[dict[str, str], str, str, str]:
    """The mascot button's attributes, its sprite, and the site name's link and text beside it."""
    match = BRAND.search(PAGES[rel].read_text(encoding="utf-8"))
    assert match, f"{rel}: the header does not start with the mascot and the site name"
    return dict(re.findall(r'([\w-]+)(?:="([^"]*)")?', match.group(1))), *match.group(2, 3, 4)


def _product(rel: str) -> str:
    return "BananaChat" if rel.startswith("bananachat/") else "BananaWiki"


def test_every_page_shows_the_mascot_beside_the_site_name(pages):
    """The header's mascot stands where the 32px icon was, with the site name linking to the home page in the
    page's language. Without the script the button stays disabled and shows the banana as a still picture."""
    sprites = set()
    for rel, page in pages.items():
        attrs, sprite, href, name = _mascot(rel)
        home = "bananachat/index.html" if rel.startswith("bananachat/") else "index.html"
        assert name == _product(rel) and _target(rel, href)[0] == _version(home, page.lang), rel
        assert {"data-mascot", "disabled"} <= attrs.keys() and attrs["data-mascot-clicks"] == "11", rel
        html = PAGES[rel].read_text(encoding="utf-8")
        assert html.count("data-mascot ") == 1 and html.count('class="mascot-sprite"') == 1, rel
        sprites.add(sprite)
    (sprite,) = sprites
    assert 'shape-rendering="crispEdges"' in sprite and 'aria-hidden="true"' in sprite


def test_the_mascot_speaks_the_page_s_language(pages):
    for rel, page in pages.items():
        attrs, _sprite, _href, name = _mascot(rel)
        label, shades, on, off = (text.format(name) for text in MASCOT_LABELS[page.lang])
        assert (attrs["aria-label"], attrs["title"], attrs["data-label-shades"]) == (label, label, shades), rel
        assert (attrs["data-on"], attrs["data-off"]) == (on, off), rel


def test_the_mascot_labels_match_the_apps():
    """BananaChat's pages word the mascot as BananaChat does; the others as BananaWiki's portal does."""
    for lang in LANGS:
        chat = _catalogue(CHAT_SRC, "bananachat", "i18n", "core.json", lang=lang)
        wiki = _catalogue(WIKI_SRC, "bananawiki", "hosting", "translations", f"{lang}.json")
        for product, catalogue, unlocked in (("BananaChat", chat, "js.mascot.unlocked"),
                                             ("BananaWiki", wiki, "js.mascot.unlocked_local")):
            words = tuple(catalogue[key] for key in ("js.mascot.label", "js.mascot.label_shades", unlocked,
                                                     "js.mascot.shades_off"))
            assert words == tuple(text.format(product) for text in MASCOT_LABELS[lang]), (lang, product)


def test_the_mascot_is_the_wiki_s_sprite():
    """Pasted from python -c "from bananawiki.core import mascot; print(mascot.svg('normal'))" in BananaWiki."""
    if not (WIKI_SRC / "bananawiki" / "core" / "mascot.py").is_file():
        pytest.skip("the BananaWiki source is not next to the site")
    sys.path.insert(0, str(WIKI_SRC))
    try:
        from bananawiki.core import mascot
    except ImportError as error:  # pragma: no cover - depends on the environment
        pytest.skip(f"BananaWiki cannot be imported here: {error}")
    finally:
        sys.path.remove(str(WIKI_SRC))
    assert {_mascot(rel)[1] for rel in PAGES} == {str(mascot.svg("normal"))}


def test_the_mascot_follows_the_wiki_s():
    """mascot.js names the version of BananaWiki's mascot it was ported from; BananaWiki's
    scripts/make_icons.py --check fails until a change there is ported here and recorded with --ported."""
    script = WIKI_SRC / "scripts" / "make_icons.py"
    if not script.is_file():
        pytest.skip(f"{script} is not next to the site")
    pytest.importorskip("PIL", reason="make_icons.py needs Pillow")
    spec = importlib.util.spec_from_file_location("make_icons", script)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.SITE_PORT == "mascot/mascot.js"
    assert tool.port(WIKI_SRC, ROOT, tool.SITE_PORT, record=False) is None


def test_pages_load_the_mascot_and_no_other_script():
    """One versioned script and one stylesheet from mascot/, both in the head; no inline script or handler."""
    for rel, path in PAGES.items():
        html = path.read_text(encoding="utf-8")
        head = html.split("<body")[0]
        prefix = "../" * rel.count("/")
        assert re.search(rf'<link rel="stylesheet" href="{prefix}mascot/mascot\.css\?v=[0-9a-f]{{12}}">', head), rel
        assert re.findall(r"<script\b[^>]*>.*?</script>", html, flags=re.DOTALL) == re.findall(
            rf'<script src="{prefix}mascot/mascot\.js\?v=[0-9a-f]{{12}}" defer></script>', head), rel
        assert html.count("<script") == 1, rel
        assert not re.search(r"<[^>]+\son\w+=", html), f"{rel}: inline event handler"


def test_every_mascot_file_is_used():
    assert sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "mascot").iterdir()) == list(MASCOT_FILES)


def test_the_policy_allows_only_the_site_s_own_script():
    """script-src 'self' for mascot.js, nothing inline; the README's header policy is the pages' plus
    frame-ancestors, which works only as a header."""
    directives = dict(part.strip().split(" ", 1) for part in CSP.split(";"))
    assert directives["script-src"] == "'self'" and "unsafe" not in CSP
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"Content-Security-Policy: {CSP}; frame-ancestors 'none'\n" in readme


def test_the_mascot_keeps_still_when_asked():
    """Less motion asked by the system: no bob, blink, hop or shower; the Konami code only leans the banana.
    The reduced-motion block comes last, as it overrides the rules before it."""
    css = (ROOT / "mascot" / "mascot.css").read_text(encoding="utf-8")
    block = css[css.rindex("@media"):]
    assert block.startswith("@media (prefers-reduced-motion: reduce) {") and block.rstrip().endswith("}\n}")
    assert ".mascot-shower { display: none; }" in block and ".mascot__body," in block
    script = (ROOT / "mascot" / "mascot.js").read_text(encoding="utf-8")
    assert 'matchMedia?.("(prefers-reduced-motion: reduce)")' in script and 'replay("mascot--lean"' in script
    assert "button.disabled = false;" in script
    assert _css_rules(".mascot:disabled .mascot__body", "mascot/mascot.css") == [" animation: none; "]


ICONS = {"img/banana_yellow.png": ("banana_yellow.png", (32, 32)),
         "img/apple-touch-icon.png": ("apple-touch-icon.png", (180, 180))}


@pytest.mark.parametrize("name", sorted(ICONS))
def test_the_icons_are_the_wiki_s_banana(name):
    """BananaWiki's scripts/make_icons.py draws them from the mascot's pixel art and writes this copy."""
    wiki_name, size = ICONS[name]
    assert _png_size(ROOT / name) == size
    source = WIKI_SRC / "bananawiki" / "wiki" / "static" / "favicons" / wiki_name
    if not source.is_file():
        pytest.skip(f"{source} is not next to the site")
    assert (ROOT / name).read_bytes() == source.read_bytes(), "run python scripts/make_icons.py in BananaWiki"


def test_every_page_links_the_favicon_and_the_home_screen_icon():
    missing = []
    for rel, path in PAGES.items():
        head = path.read_text(encoding="utf-8").split("<body")[0]
        prefix = "../" * rel.count("/")
        for tag in (f'<link rel="icon" type="image/png" href="{prefix}img/banana_yellow.png?v=',
                    f'<link rel="apple-touch-icon" href="{prefix}img/apple-touch-icon.png?v='):
            if tag not in head:
                missing.append(f"{rel}: {tag}")
    assert missing == []


def test_the_banana_logos_stay_crisp():
    """The 32x32 icon (the footer's logo, BananaChat's eyebrow) is shown at 32 CSS pixels, twice the sprite:
    high-density screens double it again without smoothing, so its pixels stay squares. The header's mascot
    draws the same sprite as SVG with crisp edges at the same size."""
    for selector in (".footer-logo img", ".eyebrow img"):
        assert _css_rules(selector) == [" width: 32px; height: 32px; image-rendering: pixelated; "], selector
    assert " width: 32px; height: 32px;" in _css_rules(".mascot .mascot-sprite", "mascot/mascot.css")[0]
    for rel, path in PAGES.items():
        footer = path.read_text(encoding="utf-8").split('<footer class="site-footer">')[1]
        assert '<a class="footer-logo" href="' in footer and 'img/banana_yellow.png?v=' in footer, rel


def test_the_screenshots_show_the_apps_with_their_banana():
    """Each app's top bar shows the banana icon at 32 pixels, so every screenshot has the icon's opaque pixels,
    exactly, near its top left corner. A screenshot of an older build fails."""
    image = pytest.importorskip("PIL.Image", reason="Pillow (one of BananaWiki's dependencies) reads the images")
    icon = image.open(ROOT / "img" / "banana_yellow.png").convert("RGBA")
    pixels = icon.load()
    art = {(x, y): pixels[x, y][:3] for y in range(icon.height) for x in range(icon.width) if pixels[x, y][3] == 255}
    anchor = min(art, key=lambda xy: (xy[1], xy[0]))  # the outline's top left pixel
    stale = []
    for path in sorted((ROOT / "img").glob("*.png")):
        if f"img/{path.name}" in ICONS:
            continue
        bar = image.open(path).convert("RGB").crop((0, 0, 320, 64))
        shot = bar.load()
        found = any(all(shot[x - anchor[0] + ax, y - anchor[1] + ay] == color for (ax, ay), color in art.items())
                    for y in range(anchor[1], bar.height - icon.height + anchor[1] + 1)
                    for x in range(anchor[0], bar.width - icon.width + anchor[0] + 1)
                    if shot[x, y] == art[anchor])
        if not found:
            stale.append(path.name)
    assert stale == [], "capture these again from the current apps"


# ── Self-hosting claims ─────────────────────────────────────────────────────


def _module(path: Path, name: str):
    if not path.is_file():
        pytest.skip(f"{path} is not next to the site")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up while the class is created
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[name]
    return module


def test_hosting_requirements_match_the_code(pages):
    """The pages' hosting requirements (optional XFS, BuildKit, Linux x86_64) match the code."""
    quotas = _module(WIKI_SRC / "bananawiki" / "ops" / "tenant_quotas.py", "site_check_tenant_quotas")
    assert (quotas.INSTALL_DEFAULT, quotas.DEFAULT) == ("auto", "auto") and "required" in quotas.MODES
    assert '"--tenant-quotas"' in (WIKI_SRC / "bananawiki" / "ops" / "cli.py").read_text(encoding="utf-8")
    assert "RUN --mount=" in (WIKI_SRC / "Dockerfile.tenant").read_text(encoding="utf-8"), "BuildKit"
    agent = (WIKI_SRC / "bananawiki" / "ops" / "runtime_agent.py").read_text(encoding="utf-8")
    assert '"x86_64"' in agent
    claims = {
        "en": ["Linux x86_64 server with Docker, including BuildKit ( docker buildx )",
               "We recommend XFS with project quotas, which the platform uses automatically to give each wiki a hard storage limit",
               "On other filesystems, the app checks uploads", "every 5 minutes"],
        "it": ["server Linux x86_64 con Docker, compreso BuildKit ( docker buildx )",
               "Ti consigliamo XFS con le quote di progetto, che la piattaforma usa automaticamente per dare a ogni wiki un limite di spazio rigido",
               "Sugli altri filesystem l’app controlla i caricamenti", "ogni 5 minuti"],
        "de": ["Linux-x86_64-Server mit Docker, einschließlich BuildKit ( docker buildx )",
               "Wir empfehlen XFS mit Projekt-Quotas, die die Plattform automatisch nutzt, um jedem Wiki eine harte Speichergrenze zu geben",
               "Auf anderen Dateisystemen prüft die App Uploads", "alle 5 Minuten"],
    }
    for rel in (rel for lang in LANGS for rel in HOMES[lang]):
        page = pages[rel]
        assert [claim for claim in claims[page.lang] if claim not in page.content] == [], rel


def test_bananachat_presets_the_pages_name_exist(pages):
    source = CHAT_SRC / "bananachat" / "services" / "provider_presets.py"
    if not source.is_file():
        pytest.skip(f"{source} is not next to the site")
    presets = set(re.findall(r'Preset\("(\w+)"', source.read_text(encoding="utf-8")))
    named = {"Anthropic": "anthropic", "OpenAI": "openai", "OpenRouter": "openrouter", "Google Gemini": "gemini",
             "Mistral": "mistral", "LM Studio": "lmstudio", "vLLM": "vllm", "llama.cpp": "llamacpp",
             "LiteLLM": "litellm"}
    assert set(named.values()) <= presets
    for lang in LANGS:
        rel = _version("bananachat/index.html", lang)
        assert [name for name in named if name not in pages[rel].content] == [], rel


# ── Legal pages ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["terms", "privacy"])
def test_legal_pages_match_across_languages(pages, name):
    en = pages[f"{name}/index.html"]
    for lang in ("it", "de"):
        other = pages[f"{name}/index.{lang}.html"]
        assert en.ids == other.ids, lang
        assert len(en.rows) == len(other.rows), lang
        assert [len(cells) for _, cells in en.rows] == [len(cells) for _, cells in other.rows], lang


@pytest.mark.parametrize("name", ["terms", "privacy"])
def test_legal_pages_say_every_language_version_counts(pages, name):
    """Each legal page lists the three published languages and says the most favourable version applies."""
    said = {"en": ("published in English, Italian and German", "most favourable"),
            "it": ("pubblicat", "in italiano, in inglese e in tedesco", "più favorevole"),
            "de": ("auf Englisch, Italienisch und Deutsch veröffentlicht", "günstigste")}
    for lang, phrases in said.items():
        content = pages[_version(f"{name}/index.html", lang)].content
        assert [phrase for phrase in phrases if phrase not in content] == [], (name, lang)


def test_pages_have_no_bracketed_notes(pages):
    """No page still carries a bracketed [CAPITALS] note to fill in."""
    bracketed = {rel: re.findall(r"\[[A-Z][A-Z .,/:-]{3,}", page.content) for rel, page in pages.items()}
    assert {rel: found for rel, found in bracketed.items() if found} == {}


def test_the_servers_stay_in_the_european_union(pages):
    """The privacy policy places the hosting provider's servers in the European Union."""
    for rel, union in (("privacy/index.html", "in the European Union"), ("privacy/index.it.html", "nell’Unione europea"),
                       ("privacy/index.de.html", "in der Europäischen Union")):
        content = pages[rel].content
        start = content.index("Hosting:")
        assert union in content[start:content.index(".", start)], rel


@pytest.fixture(scope="module")
def code():
    if not (WIKI_SRC / "bananawiki" / "hosting").is_dir():
        pytest.skip("the BananaWiki source is not next to the site")
    sys.path.insert(0, str(WIKI_SRC))
    try:
        from bananawiki.hosting import (
            accounts,
            attention,
            auth,
            email,
            instances,
            maintenance,
            oauth,
            settings,
        )
        from bananawiki.hosting import app as portal
        from bananawiki.hosting.config import ConfigError, load_config
        from bananawiki.hosting.routes import account as account_routes
        from bananawiki.hosting.routes import auth as auth_routes
        from bananawiki.hosting.routes import public as public_routes
        from bananawiki.wiki.features.auth import devices
        from bananawiki.wiki.features.users import preferences
    except ImportError as error:  # pragma: no cover - depends on the environment
        pytest.skip(f"BananaWiki cannot be imported here: {error}")
    finally:
        sys.path.remove(str(WIKI_SRC))
    return {
        "accounts": accounts, "attention": attention, "auth": auth, "email": email, "instances": instances,
        "maintenance": maintenance, "oauth": oauth, "settings": settings, "devices": devices,
        "preferences": preferences, "portal": portal, "session_cookie": portal.SESSION_COOKIE,
        "load_config": load_config, "config_error": ConfigError,
        "routes": {"account": account_routes, "auth": auth_routes, "public": public_routes},
    }


def _portal_config(code, work: Path, **settings: str):
    return code["load_config"]({"HOSTING_ENV": "test", "HOSTING_DATABASE_PATH": str(work / "hosting.db"),
                                "INSTANCES_DIR": str(work / "instances"), "BASE_DOMAIN": "example.com",
                                **settings}, secret_key="test")


@pytest.fixture(scope="module")
def defaults(code, tmp_path_factory):
    return _portal_config(code, tmp_path_factory.mktemp("hosting"))


def _source(obj) -> str:
    return _clean(inspect.getsource(obj))


def test_the_code_still_behaves_as_the_legal_pages_say(code, defaults):
    """When this fails, the hosting code changed: update the legal pages, then this test."""
    limits, maintenance = defaults.limits, code["maintenance"]
    assert limits.duration_days == 14 and limits.expiry_warning_days == (3, 1)
    assert limits.new_account_days == 7 and limits.new_account_max_instances == 1
    assert defaults.email.token_ttl_seconds == 24 * 3600
    assert code["settings"].DEFAULT_GRACE_PERIOD_DAYS == 30
    assert code["instances"].RENEWAL_WINDOW_DAYS == 7
    assert inspect.signature(code["instances"].enforce_storage_quotas).parameters["overrun_ratio"].default == 1.10
    steps = _source(maintenance._steps)
    assert '("storage suspensions", instances.lift_storage_suspensions)' in steps
    assert 'events.prune(app.config["HOSTING"].event_retention_days)' in steps
    assert defaults.event_retention_days == 3650
    assert 'get("hosting_activation_denied_timeout_seconds", 86400)' in _source(code["settings"].denied_timeout_seconds)
    assert '"password_reset_expires_at": sql_in(hours=1)' in _source(code["accounts"].issue_password_reset)
    prune = _source(maintenance._prune)
    assert 'hosting_login_attempts WHERE attempted_at < ?", (sql_in(days=-1),)' in prune
    assert 'hosting_rate_limit_hits WHERE hit_at < ?", (sql_in(days=-1),)' in prune
    assert "OR revoked_at < ?\", (sql_in(days=-30), sql_in(days=-30))" in prune
    assert "24 * 3600" in _source(maintenance._prune_uploads)
    assert code["email"].LOG_RETENTION_DAYS == 2
    assert code["attention"].NOTICE_RETENTION_DAYS == 90
    assert (code["oauth"].CODE_SECONDS, code["oauth"].TOKEN_SECONDS) == (300, 3600)
    assert code["auth"].SESSION_DAYS == 7
    # Device cookies: the portal's (hosting/auth.py) and each wiki's (wiki/features/auth/devices.py).
    assert code["auth"].DEVICE_COOKIE_DAYS == code["devices"].COOKIE_DAYS == 365
    assert "max_age=DEVICE_COOKIE_DAYS * 86400" in _source(code["auth"].set_device_cookie)
    assert "max_age=COOKIE_DAYS * 86400" in _source(code["devices"].set_cookie)
    assert 'current_app.config["SESSION_COOKIE_NAME"] + COOKIE_SUFFIX' in _source(code["devices"].cookie_name)
    # The portal keeps the chosen theme and language in plain cookies for its maintenance page.
    display = _source(code["portal"]._sync_display_cookies)
    assert "response.set_cookie(THEME_COOKIE, theme, max_age=365 * 86400" in display
    assert "response.set_cookie(LANGUAGE_COOKIE, language, max_age=365 * 86400" in display
    for script in ("hosting", "wiki"):
        source = (WIKI_SRC / "bananawiki" / script / "static" / "js" / "bananawiki.js").read_text(encoding="utf-8")
        assert '"bw_theme=" + next + ";path=/;max-age=31536000;samesite=lax"' in source, script
    assert code["preferences"].COOKIE_MAX_AGE == 365 * 86400
    assert "remember_me_days=30," in (WIKI_SRC / "bananawiki" / "wiki" / "config.py").read_text(encoding="utf-8")
    assert 'f"bw_session_{cookie}"' in (WIKI_SRC / "bananawiki" / "hosting" / "runtime" / "agent.py").read_text(
        encoding="utf-8")


# The words the privacy policies use for the code's units, cookie owners, rows and budget, by language.
PRIVACY_WORDS = {
    "en": {"days": "days", "hours": "hours", "portal": "portal", "wiki": "hosted wiki", "year": "1 year",
           "up_to": "Up to {} days", "budget": "wrong two-step codes",
           "rows": ("Email records", "Notices shown in the portal", "Failed sign-in attempts and rate-limit counters")},
    "it": {"days": "giorni", "hours": "ore", "portal": "portale", "wiki": "wiki ospitata", "year": "1 anno",
           "up_to": "Fino a {} giorni", "budget": "codici di verifica errati",
           "rows": ("Registri delle email", "Avvisi mostrati nel portale",
                    "Tentativi di accesso falliti e contatori dei limiti di frequenza")},
    "de": {"days": "Tage", "hours": "Stunden", "portal": "Portal", "wiki": "gehostetes Wiki", "year": "1 Jahr",
           "up_to": "Bis zu {} Tage", "budget": "falsche Bestätigungscodes",
           "rows": ("E-Mail-Aufzeichnungen", "Im Portal angezeigte Hinweise",
                    "Fehlgeschlagene Anmeldeversuche und Zähler für Ratenbegrenzungen")},
}


def test_privacy_policy_states_the_code_s_retention_and_cookies(pages, code):
    session_days, grace = code["auth"].SESSION_DAYS, code["settings"].DEFAULT_GRACE_PERIOD_DAYS
    minutes, hours = code["oauth"].CODE_SECONDS // 60, code["oauth"].TOKEN_SECONDS // 3600
    phrases = {
        "en": [
            f"A session lasts at most {session_days} days; its record is deleted 30 days after it expires",
            f"grace period of {grace} days", "Deleted 24 hours after the decision.",
            "Valid for 24 hours (address verification) or 1 hour (password reset)",
            f"{minutes} minutes (codes) and {hours} hour (tokens)",
            "Deleted when the download ends, and at the latest after 24 hours.",
            "exceeds its storage limit by more than 10%", "only one wiki during its first 7 days",
            "unverified for more than 24 hours", "10 years after the decision, the ordinary limitation period",
        ],
        "it": [
            f"Una sessione dura al massimo {session_days} giorni; il suo record viene eliminato 30 giorni dopo",
            f"periodo di tolleranza di {grace} giorni", "Eliminate 24 ore dopo la decisione.",
            "Validi 24 ore (verifica dell’indirizzo) o 1 ora (reimpostazione della password)",
            f"{minutes} minuti (codici) e {hours} ora (token)",
            "Eliminati al termine del download e comunque entro 24 ore.",
            "supera di oltre il 10% il proprio limite di spazio", "una sola wiki nei primi 7 giorni",
            "non verificato per più di 24 ore", "10 anni dalla decisione, il termine ordinario di prescrizione",
        ],
        "de": [
            f"Eine Sitzung dauert höchstens {session_days} Tage; ihr Datensatz wird 30 Tage nach ihrem Ablauf",
            f"Schonfrist von {grace} Tagen", "Werden 24 Stunden nach der Entscheidung gelöscht.",
            "Gültig für 24 Stunden (Bestätigung der Adresse) oder 1 Stunde (Zurücksetzen des Passworts)",
            f"{minutes} Minuten (Codes) und {hours} Stunde (Tokens)",
            "Werden gelöscht, wenn der Download endet, spätestens aber nach 24 Stunden.",
            "sein Speicherlimit um mehr als 10 % überschreitet", "in seinen ersten 7 Tagen nur ein Wiki haben",
            "länger als 24 Stunden nicht bestätigt", "10 Jahre nach der Entscheidung, die ordentliche Verjährungsfrist",
        ],
    }
    for lang, words in PRIVACY_WORDS.items():
        rel = _version("privacy/index.html", lang)
        rows, days = pages[rel].table(), words["days"]
        emails, notices, attempts = words["rows"]
        assert rows[emails] == [f"{code['email'].LOG_RETENTION_DAYS} {days}."], rel
        assert rows[notices] == [f"{code['attention'].NOTICE_RETENTION_DAYS} {days}."], rel
        assert rows[attempts] == [f"24 {words['hours']}."], rel
        text = pages[rel].content
        for phrase in phrases[lang]:
            assert phrase in text, f"{rel}: {phrase!r}"
        session, device = code["session_cookie"], code["auth"].DEVICE_COOKIE
        wiki_device = "bw_session_<wiki>" + code["devices"].COOKIE_SUFFIX
        accessibility = code["preferences"].COOKIE
        portal, wiki = words["portal"], words["wiki"]
        durations = {
            f"__Host-{session} ({portal})": words["up_to"].format(session_days),
            f"__Host-{device} ({portal})": f"{code['auth'].DEVICE_COOKIE_DAYS} {days}",
            f"__Host-bw_session_<wiki> ({wiki})": f"30 {days}",
            f"__Host-{wiki_device} ({wiki})": f"{code['devices'].COOKIE_DAYS} {days}",
            code["portal"].THEME_COOKIE: words["year"],
            f"{code['portal'].LANGUAGE_COOKIE} ({portal})": words["year"],
            f"{accessibility} ({wiki})": f"{code['preferences'].COOKIE_MAX_AGE // 86400} {days}",
        }
        cookie_rows = {name: cells for name, cells in rows.items() if name.startswith(("__Host-", "bw_"))}
        assert sorted(cookie_rows) == sorted(durations), f"{rel}: the cookie table lists other cookies"
        for name, duration in durations.items():
            assert duration in cookie_rows[name][-1], f"{rel}: {name}"
        # A device cookie also gives a known browser its own budget of wrong two-step codes.
        assert words["budget"] in cookie_rows[f"__Host-{device} ({portal})"][0], rel


def test_terms_state_the_code_s_trial_rules(pages, code, defaults):
    limits = defaults.limits
    grace, window = code["settings"].DEFAULT_GRACE_PERIOD_DAYS, code["instances"].RENEWAL_WINDOW_DAYS
    warn = " and ".join(f"{days} day{'s' if days > 1 else ''}" for days in limits.expiry_warning_days)
    avvisi = " e ".join(f"{days} giorn{'i' if days > 1 else 'o'}" for days in limits.expiry_warning_days)
    tage = " und ".join(f"{days} Tag{'e' if days > 1 else ''}" for days in limits.expiry_warning_days)
    for rel, phrases in (
        ("terms/index.html", [
            f"the term is {limits.duration_days} days", f"We email the owner {warn} before the end date",
            "that it has no end date, the wiki does not expire", f"can renew it during its last {window} days",
            "a new full term counted from the renewal", f"grace period of {grace} days",
            "exceeds its limit by more than 10% is suspended automatically",
            "It reopens automatically as soon as it fits within its limit again",
            f"only one wiki during its first {limits.new_account_days} days",
            "deleted 24 hours after the decision", "If you do not confirm a new address within 24 hours",
            "(Article 16 DSA)", "(Article 17 DSA)", "(Article 11 DSA)",
            "(Article 12 DSA)", "Article 1229 of the Italian Civil Code", "at least 14 years old",
            "discontinued on 20 July 2025",
        ]),
        ("terms/index.it.html", [
            f"la durata è di {limits.duration_days} giorni", f"Inviamo un’email al proprietario {avvisi} prima",
            "che la wiki non ha una data di fine, la wiki non scade", f"può rinnovarla negli ultimi {window} giorni",
            "una nuova durata completa a partire dal rinnovo", f"periodo di tolleranza di {grace} giorni",
            "supera il limite di oltre il 10% viene sospesa automaticamente",
            "La wiki si riapre da sola appena rientra nel limite",
            f"una sola wiki nei primi {limits.new_account_days} giorni",
            "eliminata 24 ore dopo la decisione", "Se non confermi un nuovo indirizzo entro 24 ore",
            "(articolo 16 DSA)", "(articolo 17 DSA)", "(articolo 11 DSA)",
            "(articolo 12 DSA)", "articolo 1229 del codice civile", "almeno 14 anni", "chiusa il 20 luglio 2025",
        ]),
        ("terms/index.de.html", [
            f"beträgt die Laufzeit {limits.duration_days} Tage", f"Wir senden dem Eigentümer {tage} vor dem Enddatum",
            "dass es kein Enddatum hat, läuft das Wiki nicht ab", f"es in seinen letzten {window} Tagen erneuern",
            "eine neue volle Laufzeit ab der Erneuerung", f"Schonfrist von {grace} Tagen",
            "sein Limit um mehr als 10 % überschreitet, wird automatisch gesperrt",
            "Es wird automatisch wieder geöffnet, sobald es wieder in sein Limit passt",
            f"in seinen ersten {limits.new_account_days} Tagen nur ein Wiki haben",
            "24 Stunden nach der Entscheidung gelöscht", "Wenn du eine neue Adresse nicht innerhalb von 24 Stunden",
            "(Artikel 16 DSA)", "(Artikel 17 DSA)", "(Artikel 11 DSA)",
            "(Artikel 12 DSA)", "Artikel 1229 des italienischen Zivilgesetzbuches", "mindestens 14 Jahre alt",
            "am 20. Juli 2025 eingestellt",
        ]),
    ):
        text = pages[rel].content
        missing = [phrase for phrase in phrases if phrase not in text]
        assert missing == [], rel
        assert "ec.europa.eu/consumers/odr" not in " ".join(pages[rel].links)


def _published_terms_version(pages) -> str:
    versions = set()
    for rel in (_version(f"{name}/index.html", lang) for name in ("terms", "privacy") for lang in LANGS):
        found = re.findall(r"\bVersion[e]? (\d{4}-\d{2}-\d{2})\b", pages[rel].content)
        assert len(found) == 1, rel
        versions |= set(found)
    assert len(versions) == 1, versions
    return versions.pop()


def test_legal_pages_show_one_version_that_the_portal_can_record(pages, code, tmp_path):
    """The six legal pages share a version that HOSTING_TERMS_VERSION and HOSTING_TERMS_REQUIRED_VERSION
    can record; the portal refuses a required version later than the current one."""
    published = _published_terms_version(pages)
    assert code["accounts"].TERMS_VERSION <= published, "the built-in TERMS_VERSION names terms that are not published"
    configured = _portal_config(code, tmp_path, HOSTING_TERMS_VERSION=published,
                                HOSTING_TERMS_REQUIRED_VERSION=published)
    assert (configured.terms_version, configured.terms_required_version) == (published, published)
    later = f"{int(published[:4]) + 1}{published[4:]}"
    with pytest.raises(code["config_error"]):
        _portal_config(code, tmp_path, HOSTING_TERMS_VERSION=published, HOSTING_TERMS_REQUIRED_VERSION=later)


def test_the_terms_gate_works_as_the_terms_say(pages, code):
    """Terms section 17: until new terms are accepted, the portal, its API and wiki sign-in wait."""
    auth, routes = code["auth"], code["routes"]
    assert "terms" in auth.GATES
    still_open = [routes["public"].terms, routes["public"].privacy, routes["account"].accept_terms,
                  routes["account"].export_account, routes["account"].delete_account, routes["auth"].logout]
    assert [view.__name__ for view in still_open if not auth.is_exempt(view, "terms")] == []
    assert "accounts.terms_outdated(account)" in _source(code["oauth"].account_may_sign_in)
    api = (WIKI_SRC / "bananawiki" / "hosting" / "routes" / "api.py").read_text(encoding="utf-8")
    assert "if accounts.terms_outdated(account):" in api
    for rel, phrases in (
        ("terms/index.html", ["The portal may also ask you to accept the new terms before you continue to use it",
                              "Until you do, its API and signing in to wikis with your account are paused",
                              "you can still read the terms, download your data, delete your account or sign out"]),
        ("terms/index.it.html", ["Il portale può anche chiederti di accettare i nuovi termini prima di continuare a usarlo",
                                 "Finché non li accetti, le sue API e l’accesso alle wiki con il tuo account restano sospesi",
                                 "puoi comunque leggere i termini, scaricare i tuoi dati, eliminare il tuo account o uscire"]),
        ("terms/index.de.html", ["Das Portal kann dich außerdem bitten, die neuen Bedingungen zu akzeptieren, bevor du es "
                                 "weiter nutzt",
                                 "Bis du das tust, sind seine API und die Anmeldung bei Wikis mit deinem Konto ausgesetzt",
                                 "du kannst weiterhin die Bedingungen lesen, deine Daten herunterladen, dein Konto löschen "
                                 "oder dich abmelden"]),
    ):
        text = _clean(pages[rel].content)
        assert [phrase for phrase in phrases if phrase not in text] == [], rel
