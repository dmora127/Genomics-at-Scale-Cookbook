#!/usr/bin/env python3
"""Keep the citation quoted on the landing page (index.md) in step with CITATION.cff.

index.md shows readers how to cite the cookbook as a blockquote. This script renders that quote from
CITATION.cff, so the names, year, version and DOI in it never fall behind the citation file that the other
scripts maintain (sync-citation.py for the authors, sync-release-doi.py for a release's DOIs):

  > Morales, D. A., Lombardi, R., & Koch, C. (2026). *Genomics at Scale Cookbook* (Version 1.0.0). Center for
  > High Throughput Computing, University of Wisconsin-Madison. https://doi.org/10.5281/zenodo.1003149

The quote is APA style: authors as "Family, G. I." joined with commas and an ampersand before the last one
(an author entity's name is used as written); the year of date-released, or n.d. without one; the title in
italics with the version in parentheses; the authors' distinct affiliations as the publisher; and the DOI as a
URL, or the repository-code or url field when there is no DOI yet.

The quote is found through the marker comment above it in index.md (MyST renders a % line as nothing):

  % Generated from CITATION.cff by .github/scripts/sync-index-citation.py ...
  > Morales, D. A. ...

The blockquote lines after the marker (blank lines between them are kept) are replaced; nothing else in the
page is touched. Without the marker the script stops with an error rather than guess where the quote is.

Usage:
  sync-index-citation.py            rewrite index.md when its quote is out of date (exit 0)
  sync-index-citation.py --check    change nothing; exit 1 with a diff when index.md would be rewritten

Both modes exit 1 on a problem: a CITATION.cff that cannot be read or names no authors, or an index.md without
the marker. Run from anywhere inside the repository; the files are found next to the .github directory.
Requires PyYAML.
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CITATION_FILE = ROOT / "CITATION.cff"
INDEX_FILE = ROOT / "index.md"
MARKER_PREFIX = "% Generated from CITATION.cff"


def initials(given):
    """'D. A.' from 'Daniel A.', 'J.-L.' from 'Jean-Luc'."""
    return " ".join("-".join(piece[0] + "." for piece in token.split("-") if piece) for token in str(given).split())


def author_name(author):
    """'Morales, D. A.' for a person, the name as written for an entity."""
    if author.get("name") and not author.get("family-names"):
        return str(author["name"]).strip()
    family = " ".join(str(author[key]).strip() for key in ("name-particle", "family-names") if author.get(key))
    text = ", ".join(part for part in (family, initials(author.get("given-names", ""))) if part)
    if author.get("name-suffix"):
        text += f", {str(author['name-suffix']).strip()}"
    return text


def author_list(names):
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + f", & {names[-1]}"


def citation(cff, problems):
    """The APA-style sentence for a CITATION.cff mapping, or None when it has no authors."""
    authors = [a for a in cff.get("authors") or [] if isinstance(a, dict)]
    if not authors:
        problems.append("::error file=CITATION.cff::no authors to cite")
        return None
    released = str(cff.get("date-released") or "")
    year = released[:4] if re.match(r"\d{4}", released) else "n.d."
    title = str(cff.get("title") or "").strip() or "Untitled"
    version = cff.get("version")
    publisher = "; ".join(dict.fromkeys(str(a["affiliation"]).strip() for a in authors if a.get("affiliation")))
    link = f"https://doi.org/{cff['doi']}" if cff.get("doi") else str(cff.get("repository-code") or cff.get("url") or "")
    pieces = [f"{author_list([author_name(a) for a in authors])} ({year}).",
              f"*{title}*" + (f" (Version {version})" if version not in (None, "") else "") + "."]
    if publisher:
        pieces.append(publisher + ".")
    if link:
        pieces.append(link)
    return " ".join(pieces)


def rewrite(text, quote, problems):
    """index.md with the blockquote after the marker replaced by the quote, or None when there is no marker."""
    lines = text.splitlines(keepends=True)
    marker = next((i for i, line in enumerate(lines) if line.startswith(MARKER_PREFIX)), None)
    if marker is None:
        problems.append(f"::error file=index.md::no line starting with '{MARKER_PREFIX}' above the citation quote; "
                        "add that marker comment and the quote will be kept current")
        return None
    start = marker + 1
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    end = start
    while end < len(lines) and lines[end].startswith(">"):
        end += 1
    new_lines = [f"> {quote}\n"]
    if end < len(lines) and lines[end].strip() != "":
        new_lines.append("\n")
    return "".join(lines[:start] + new_lines + lines[end:])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when index.md would change; write nothing")
    args = parser.parse_args()

    problems = []
    try:
        cff = yaml.safe_load(CITATION_FILE.read_text())
        text = INDEX_FILE.read_text()
    except (OSError, yaml.YAMLError) as error:
        sys.exit(f"sync-index-citation: cannot read the inputs: {error}")
    if not isinstance(cff, dict):
        problems.append("::error file=CITATION.cff::not a mapping")
    quote = citation(cff, problems) if not problems else None
    new = rewrite(text, quote, problems) if quote else None
    for message in problems:
        print(message)
    if problems:
        print(f"sync-index-citation: {len(problems)} problem(s) to fix by hand; index.md left as it is")
        return 1
    if new == text:
        print("sync-index-citation: index.md already quotes the current CITATION.cff")
        return 0
    if args.check:
        print("::error file=index.md::the citation quote is out of date; run python3 .github/scripts/sync-index-citation.py and commit the result")
        print("".join(difflib.unified_diff(text.splitlines(True), new.splitlines(True), "index.md", "index.md (synced)")))
        return 1
    INDEX_FILE.write_text(new)
    print(f"rewrote index.md: {quote}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
