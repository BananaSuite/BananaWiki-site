# bananawiki.com

Source of the bananawiki.com website, the landing site for
[BananaWiki](https://github.com/BananaSuite/BananaWiki),
[BananaChat](https://github.com/BananaSuite/BananaChat),
[BananaGit](https://github.com/BananaSuite/BananaGit) and
[BananaVibe](https://github.com/BananaSuite/BananaVibe). It is plain HTML, one
stylesheet and the header's mascot, with no build step. Maintained by Luca Zani
and contributors.

## Files

```text
index.html, index.*.html                 home pages, English, Italian and German
unavailable.html, unavailable.*.html     home pages for when hosted sign-up is closed
about/, terms/, privacy/                 information and policy pages, English, Italian and German
bananachat/                              BananaChat pages, English, Italian and German
bananagit/, bananavibe/                  BananaGit and BananaVibe pages, English, Italian and German
style.css                                shared stylesheet
mascot/                                  script and styles of the mascot in the header
img/                                     icons and screenshots
CNAME, .nojekyll                         static hosting metadata
LICENSE                                  GNU AGPL version 3
tests/                                   checks for the pages
screenshots/                             capture scripts for the screenshots
.github/workflows/screenshots.yml        daily recapture of the screenshots
```

## Preview and update

From the repository root:

```sh
python3 -m http.server 8080 --bind 127.0.0.1
```

Open http://127.0.0.1:8080 and check all three languages and a phone-width
layout after every edit.

Keep the English, Italian and German pages in sync, including the three
`unavailable` home pages. Every page names its other two language versions as
`hreflang` alternates and links to them in the header. The normal and
unavailable home pages share their features, screenshots, self-hosting and
story sections between `<!-- shared:NAME -->` markers; edit both copies of a
section together.

On the about, terms, privacy and BananaChat pages, elements marked
`data-only="unavailable"` are hidden by style.css. For the closed sign-up
variant, delete the elements marked `data-only="available"` and remove the
attribute from the others, then copy unavailable.html, unavailable.it.html and
unavailable.de.html over index.html, index.it.html and index.de.html in the
publication directory.

## Structure and style

Every page has the same frame: a skip link, `header.site-header` (the mascot
and `.brand-name`, then `nav.nav` with the page's links, the other languages
and one `.nav-button`), `main#content` and `footer.site-footer`. The home and
BananaChat pages are made of `section.section` blocks, each starting with a
`header.section-header`; the hero screenshot sits in `.band`, the yellow strip
that starts behind its lower part and holds its caption and `dl.facts`. The The
about, terms and privacy pages are one `article.page`.

style.css is written mobile first: the base rules are the phone layout and
the `min-width` media queries add columns. On phones the header's links are
one row that scrolls sideways, the hero buttons are full width and each
gallery is a row of screenshots to swipe through. Colours, fonts and sizes are custom
properties on `:root` (`--color-bg`, `--color-text`, `--color-accent`,
`--color-band` and so on); use them rather than new values. Yellow is for the
primary buttons, focus rings and the band; everything else stays in the greys.

Copy conventions:

* English uses British spelling (colour, organise, labelled, enrolment,
  catalogue, licence as the noun), as both apps do.
* Quote as few interface labels as possible, and quote them as each app shows
  them: both apps' account menus say Appearance (Aspetto, Darstellung). In
  Italian, write "la wiki" ("le wiki" in the plural), "Editor visuale delle
  pagine" and "schede" for kanban cards. In German, write "das Wiki", address
  the reader as "du" and use the German interface's words ("Darstellung",
  "Seitenbaukasten", "Karten" on kanban boards).
* Credit the project to "Luca Zani and contributors" ("Luca Zani e
  collaboratori", "Luca Zani und Mitwirkende"). Only the about pages tell where
  the project started.
* Mark links to documentation that exists only in English, "(in inglese)" and
  "(auf Englisch)".
* Describe only features that exist in the current release, and say which
  ones are optional.

## Screenshots

Capture screenshots from disposable instances of the current apps with
sample data, never from a real deployment. Use English, the dark theme and a
1280 by 800 viewport. The hosting dashboard is captured in the portal's dark
theme, as the published image always was. The hero screenshots (`wiki-home.png`, `bananachat.png`,
`bananagit.png` and `bananavibe.png`) must be exactly 1280 by 800: the yellow band is drawn for
that shape, and a test checks it. The gallery and the hosting section show a
16:10 preview cut from the top of each image and link to the whole file, so
long pages (API keys, providers, subscription pools) can be full-page captures
at the same width. Each app's top bar shows the banana icon, and a test checks
that every screenshot contains it. A capture with a dialog open (the image
options) is taken with the dialog's backdrop made transparent, so the top bar
keeps its colours.

The pages use these captures: the wiki home, the editor, the image options,
Appearance, a Kanban board, a canvas, the features page of the administration
and the hosting dashboard (`wiki-home`, `editor`, `editor-images`,
`wiki-customize`, `kanban`, `canvas`, `plugins`, `hosting-dashboard`), and for
BananaChat a conversation, the model picker, Appearance, a cloud session, the
API page, the providers and a subscription pool (`bananachat`,
`bananachat-models`, `bananachat-customize`, `bananachat-cloud-session`,
`bananachat-api`, `bananachat-providers`, `bananachat-claude-pool`), and for
BananaGit a repository, its issues and a pull request (`bananagit`,
`bananagit-issues`, `bananagit-pull-request`), and for BananaVibe its
dashboard, drawn from the terminal's output during a run with scripted
stand-in agents (`bananavibe`). Each
image's `alt` text describes what the capture shows; update it with the image.

After replacing an image:

1. Compress it losslessly, for example with `oxipng -o max --zopfli`.
2. Update the `width` and `height` attributes wherever the image appears.
3. Update its `?v=` version everywhere it is linked. The version is the first
   twelve characters of the file's SHA-256 digest:

   ```sh
   sha256sum img/kanban.png | cut -c1-12
   ```

   An image's link and its `src` use the same version. style.css is versioned
   the same way.

Delete images that no page uses any more; a test fails on unused files in
img/.

`img/banana_yellow.png` (32x32) and `img/apple-touch-icon.png` (180x180) are
copies of BananaWiki's icons. BananaWiki's `scripts/make_icons.py` draws them
and writes these copies when this checkout sits next to BananaWiki.

### Automatic captures

`screenshots/apps.json` lists the apps: their repository, the command that
builds a checkout, whether `screenshots/` has a capture module for them, and
the commit their published screenshots were taken from. A module is
`screenshots/NAME.py` with a `capture(src, page, shoot)` function: it starts a
throwaway instance from the built checkout in `src`, fills it with sample
data and calls `shoot("file.png")` for each image.

```sh
python3 -m pip install playwright pillow pyte && python3 -m playwright install chromium
python3 screenshots/capture.py --outdated                # apps whose repository has moved
python3 screenshots/capture.py bananagit --src ../BananaGit
```

A capture writes the images to img/, compresses them, updates their `?v=`
versions, widths and heights on every page and records the commit.
`.github/workflows/screenshots.yml` does this once a day for every app whose
repository has moved, runs the tests and commits the result to this
repository; it can also be started by hand, with an option to recapture
everything. BananaWiki, BananaChat, BananaGit and BananaVibe each have a
module; an app
listed without one is only reported in the run's summary. New images,
captions and `alt` texts are still added to the pages by hand; the workflow
replaces images that pages already show.

Nothing real stands behind the sample data. BananaChat's answers come from
the imitation model server and sandbox runner of its own tests, and its
subscription pool from a stand-in for the Claude Code command. The hosting
dashboard comes from the portal with its in-memory runtime, so no containers
exist and the storage figures are sample numbers. The modules use the apps'
own commands, APIs and forms where they can, and a few internals where they
cannot; when an app changes those, the capture fails and the old images
stay.

## Mascot

The banana in each page's header is BananaWiki's mascot, as in the apps' top
bars: it hops when clicked, eleven clicks in a row put its sunglasses on (kept
in the browser) and eleven more take them off, and the Konami code sends a
shower of small bananas. Its files are a port of BananaWiki's
`bananawiki/core/mascot.py` and `bananawiki/core/static/mascot/`:

* `mascot/mascot.js`: the behaviour. It reads the labels from the button.
* `mascot/mascot.css`: the animations, with a block at the end that keeps the
  banana still when the system asks for less motion.
* The button in each page's header: the sprite, pasted from
  `python -c "from bananawiki.core import mascot; print(mascot.svg('normal'))"`
  run in BananaWiki, and the labels in the page's language. The button is
  disabled in the HTML and enabled by the script, so without JavaScript it is
  a still picture.

The first comment in mascot.js names the version of BananaWiki's mascot it
follows. When that mascot changes, `scripts/make_icons.py --check` in
BananaWiki fails while this checkout sits next to it; port the change, run
`python scripts/make_icons.py --ported` there to record the new version, then
update the `?v=` versions of mascot.js and mascot.css on every page.

## Legal pages

The terms and privacy pages describe the BananaWiki hosting portal with its
default settings (trial length, warnings, grace period, retention periods and
cookies). If you run the portal with other settings, change the pages to
match. The `Version` line on the six legal pages must match the portal's
`HOSTING_TERMS_VERSION`, so that accounts record the version they accepted.

## Tests

```sh
python3 -m pip install pytest pillow
python3 -m pytest -p no:cacheprovider tests
```

The tests check page structure, the Content Security Policy, links and
fragments, asset versions, image sizes, unused images, the mascot on every
page and its labels, the language versions, spelling and the attribution rules
above. With BananaWiki and BananaChat checked out next to this repository
(or `BANANAWIKI_SRC` and `BANANACHAT_SRC` pointing at them), they also compare
the pages with the apps: interface labels, the wiki's interface languages,
hosting requirements, BananaChat's provider presets and the mascot's sprite,
labels and ported version. With BananaWiki's dependencies installed, they
check that the legal pages state the retention periods, cookies and terms
rules of the hosting code. Checks whose sources are missing are skipped.
`SITE_ROOT` runs the tests against another copy of the site.

## Publishing

Upload the HTML files, style.css, img/, mascot/, about/, terms/, privacy/,
bananachat/, bananagit/, bananavibe/, CNAME and .nojekyll to the site root, keeping the directory
layout. Remove published files that the update deleted. Keep `.git/`,
credentials and other private files out of the web root.

For GitHub Pages, select the publishing branch and its root directory in the
repository's Pages settings; CNAME carries the domain. Pages then also serves
README.md, LICENSE and tests/, which is harmless.

Every page has a Content Security Policy that allows only local images,
styles and scripts, and no inline script. Where the host supports response
headers, also send:

```text
Content-Security-Policy: default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'none'; object-src 'none'; frame-ancestors 'none'
Referrer-Policy: strict-origin-when-cross-origin
X-Content-Type-Options: nosniff
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

`frame-ancestors` only works as a header, not in a meta tag.

Email addresses on the pages sit between `<!--email_off-->` and
`<!--/email_off-->`. Some CDNs rewrite addresses into a form that only their
own script decodes; these markers tell them to leave the address alone. Keep
any new address inside them.

## Licence

The site is licensed under the GNU Affero General Public License version 3
only (`AGPL-3.0-only`), like BananaWiki, BananaChat and BananaVibe; see
[LICENSE](LICENSE). This covers the HTML, the stylesheet, the script, the
images, the tests and the text of every page.

## Security

Report security problems in the site or the hosted service as described in
[BananaWiki's security policy](https://github.com/BananaSuite/BananaWiki/blob/main/SECURITY.md),
not in public issues.
