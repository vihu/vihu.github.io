#!/usr/bin/env python3
"""Check that local links in index.html resolve and that shared PDFs are intact."""

import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
SKIP_PREFIXES = ("http:", "https:", "//", "mailto:", "data:", "javascript:", "#")
EOF_WINDOW = 1024
# Tiddler types whose body can hold raw HTML. TiddlyWiki treats a missing type as wikitext.
MARKUP_TYPES = ("", "text/vnd.tiddlywiki", "text/html")


class LinkCollector(HTMLParser):
    """Collect href and src values from the page and from the markup tiddlers it stores.

    TiddlyWiki stores each tiddler as <div title=...><pre>escaped body</pre></div>, so
    links written in a tiddler (such as the resume button) only show up once the
    unescaped body is parsed as HTML in turn.
    """

    def __init__(self):
        super().__init__()
        self.targets = []
        self.tiddler_type = None
        self.body = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and "title" in attrs:
            self.tiddler_type = attrs.get("type") or ""
        elif tag == "pre" and self.tiddler_type in MARKUP_TYPES:
            self.body = []
        for name in ("href", "src"):
            if attrs.get(name):
                self.targets.append(attrs[name].strip())

    def handle_data(self, data):
        if self.body is not None:
            self.body.append(data)

    def handle_endtag(self, tag):
        if tag == "pre" and self.body is not None:
            inner = LinkCollector()
            inner.feed("".join(self.body))
            inner.close()
            self.targets.extend(inner.targets)
            self.body = None
            self.tiddler_type = None


def local_path(target):
    """Return the repo-relative path a link points to, or None to skip it."""
    if target.lower().startswith(SKIP_PREFIXES):
        return None
    path = unquote(urlsplit(target).path).lstrip("/")
    return path or None


def resolves(path):
    full = (ROOT / path).resolve()
    if not full.is_relative_to(ROOT):
        return False
    return full.is_file() or (full / "index.html").is_file()


def check_links(problems):
    index = ROOT / "index.html"
    if not index.is_file():
        problems.append("index.html: file is missing")
        return 0
    collector = LinkCollector()
    collector.feed(index.read_text(encoding="utf-8"))
    count = 0
    for target in collector.targets:
        path = local_path(target)
        if path is None:
            continue
        count += 1
        if not resolves(path):
            problems.append(
                f"index.html: broken link {target!r}: {path} does not exist"
            )
    return count


def check_pdfs(problems):
    pdfs = sorted((ROOT / "shared").glob("*.pdf"))
    for pdf in pdfs:
        name = pdf.relative_to(ROOT).as_posix()
        data = pdf.read_bytes()
        if not data:
            problems.append(f"{name}: file is empty")
        elif not data.startswith(b"%PDF-"):
            problems.append(f"{name}: does not start with %PDF-")
        elif b"%%EOF" not in data[-EOF_WINDOW:]:
            problems.append(
                f"{name}: no %%EOF in the last {EOF_WINDOW} bytes (truncated?)"
            )
    return len(pdfs)


def main():
    problems = []
    links = check_links(problems)
    pdfs = check_pdfs(problems)
    for problem in problems:
        print(f"FAIL {problem}")
    if problems:
        print(f"{len(problems)} problem(s) found")
        return 1
    print(
        f"OK: {links} local link(s) in index.html resolve, {pdfs} PDF(s) in shared/ are valid"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
