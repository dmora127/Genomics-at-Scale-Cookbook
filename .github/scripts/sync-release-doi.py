#!/usr/bin/env python3
"""Record a release's Zenodo DOIs in CITATION.cff (and the DOI badge in README.md).

When a GitHub release is published, Zenodo archives it and mints two DOIs: a concept DOI, created with the
first release and shared by every version, which always resolves to the latest one; and a version DOI for
that release alone. This script finds the Zenodo record for a release tag and writes both into CITATION.cff:

  doi: 10.5281/zenodo.1003149                             <- the concept DOI is the primary DOI
  identifiers:
    - description: "The concept DOI of the work."
      type: doi
      value: 10.5281/zenodo.1003149
    - description: "The versioned DOI for version 1.1.0 of the work."
      type: doi
      value: 10.5281/zenodo.4813122
  version: 1.1.0                                          <- the tag, without a leading v
  date-released: "2026-11-02"                             <- the record's publication date

Those four top-level keys are the only ones it touches, kept together at the end of the file; every other line
stays exactly as it is (sync-citation.py owns the authors list). Later releases keep the concept entry and
replace the version entry, version and date-released, so identifiers always has exactly these two entries.
The concept DOI never changes silently: when CITATION.cff already carries a different primary doi the script
stops with an error, because a repository has one concept DOI and a record under another one means something
went wrong on Zenodo's side (or the integration was recreated). Pass --replace-concept-doi to accept it.

With --badge README.md the Zenodo badge for the concept DOI is added under the first heading of that file,
once; a file that already has a badge is left alone.

The record is found through Zenodo's public API (no token) by the related identifier Zenodo attaches to every
GitHub release, https://github.com/OWNER/REPO/tree/TAG, double-checked against the record's version, which
Zenodo sets to the tag verbatim. Zenodo processes a release asynchronously, so right after publishing there is
no record yet: --wait polls until there is one or --timeout seconds have passed.

Usage:
  sync-release-doi.py TAG [--repo OWNER/REPO] [--wait] [--timeout 2700] [--interval 60] [--badge README.md]
  sync-release-doi.py TAG --check                 change nothing; exit 1 with a diff when a file would change
  sync-release-doi.py TAG --version-doi DOI --concept-doi DOI --date-released YYYY-MM-DD
                                                  offline: write the given values, no lookup
  sync-release-doi.py TAG --api https://sandbox.zenodo.org/api

--repo defaults to $GITHUB_REPOSITORY. Exit 0 when the files were written or already record the release;
exit 1, writing nothing, when there is no record for the tag (at once, or after the --wait budget), the
concept DOI would change, or the rewritten file does not read back as intended. Run from anywhere inside the
repository; the files are found next to the .github directory. Requires PyYAML.
"""
import argparse
import difflib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CITATION_FILE = ROOT / "CITATION.cff"
MANAGED_KEYS = ("doi", "identifiers", "version", "date-released")
DOI = re.compile(r"10\.\d{4,9}(\.\d+)?/\S+")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
TOP_KEY = re.compile(r"([A-Za-z][A-Za-z0-9_-]*):(?:\s|$)")
CONCEPT_TEXT = "The concept DOI of the work."
VERSION_TEXT = "The versioned DOI for version {version} of the work."
BADGE = "[![DOI](https://zenodo.org/badge/DOI/{doi}.svg)](https://doi.org/{doi})"
DEFAULT_API = "https://zenodo.org/api"


class Transient(Exception):
    """A network problem worth retrying."""


class Fatal(Exception):
    """A problem a person has to look at."""


def cff_version(tag):
    """'1.0.0' for the tag 'v1.0.0' or '1.0.0': CFF's version is the bare number."""
    return tag[1:] if re.fullmatch(r"[vV]\d.*", tag) else tag


def tree_url(repo, tag):
    return f"https://github.com/{repo}/tree/{tag}"


def api_get(url, repo):
    request = urllib.request.Request(url, headers={"User-Agent": f"sync-release-doi (https://github.com/{repo})",
                                                   "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 429 or error.code >= 500:
            raise Transient(f"HTTP {error.code} from {url}") from error
        raise Fatal(f"HTTP {error.code} from {url}") from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise Transient(f"{error} ({url})") from error


def find_record(api, repo, tag):
    """The Zenodo record for a release tag, or None while there is none."""
    url = tree_url(repo, tag)
    query = urllib.parse.urlencode({"q": f'metadata.related_identifiers.identifier:"{url}"',
                                    "all_versions": "true", "size": 10})
    data = api_get(f"{api}/records?{query}", repo)
    hits = []
    for hit in ((data.get("hits") or {}).get("hits") or []) if isinstance(data, dict) else []:
        metadata = hit.get("metadata") or {}
        related = {str(r.get("identifier", "")).lower()
                   for r in metadata.get("related_identifiers") or [] if isinstance(r, dict)}
        if url.lower() in related and str(metadata.get("version")) == tag:
            hits.append(hit)
    if len(hits) > 1:
        raise Fatal(f"Zenodo has {len(hits)} records for {url} ({', '.join(str(h.get('doi')) for h in hits)}); "
                    "a release has one record, so look at them on Zenodo before recording either")
    return hits[0] if hits else None


def wait_for_record(api, repo, tag, wait, timeout, interval):
    """Poll for the record until it exists or the budget is spent (one attempt without --wait); None on timeout."""
    started = time.monotonic()
    while True:
        try:
            record = find_record(api, repo, tag)
            if record is not None:
                return record
            reason = "no record yet"
        except Transient as error:
            if not wait:
                raise Fatal(f"could not query Zenodo: {error}") from error
            reason = f"request failed: {error}"
        elapsed = time.monotonic() - started
        if not wait or elapsed + interval > timeout:
            return None
        print(f"waiting for Zenodo ({reason}); {int(elapsed // 60)} min elapsed, trying again in {interval} s", flush=True)
        time.sleep(interval)


def release_facts(tag, record=None, overrides=None):
    """{tag, version, concept, version_doi, date} for the release, checked for shape."""
    if record is not None:
        metadata = record.get("metadata") or {}
        facts = {"concept": record.get("conceptdoi"), "version_doi": record.get("doi"),
                 "date": metadata.get("publication_date")}
    else:
        facts = dict(overrides)
    facts = {key: (str(value).strip() if value is not None else None) for key, value in facts.items()}
    facts.update(tag=tag, version=cff_version(tag))
    errors = []
    for key, label in (("concept", "concept DOI"), ("version_doi", "version DOI")):
        if not facts[key] or not DOI.fullmatch(facts[key]):
            errors.append(f"{label} {facts[key]!r} is not a DOI")
    if not facts["date"] or not DATE.fullmatch(facts["date"]):
        errors.append(f"publication date {facts['date']!r} is not YYYY-MM-DD")
    if errors:
        raise Fatal(f"the release data for {tag} is not usable: " + "; ".join(errors))
    return facts


def quoted(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def scalar(value):
    """A YAML scalar in CITATION.cff's house style: plain when simple text that YAML reads back unchanged, else quoted."""
    value = str(value)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ./'()\-]*[A-Za-z0-9.)]", value) and yaml.safe_load(value) == value:
        return value
    return quoted(value)


def render(facts):
    """The text of each managed top-level block, and what the file must read back as."""
    concept, version_doi = facts["concept"], facts["version_doi"]
    version_text = VERSION_TEXT.format(version=facts["version"])
    blocks = {
        "doi": f"doi: {scalar(concept)}\n",
        "identifiers": ("identifiers:\n"
                        f"  - description: {quoted(CONCEPT_TEXT)}\n    type: doi\n    value: {scalar(concept)}\n"
                        f"  - description: {quoted(version_text)}\n    type: doi\n    value: {scalar(version_doi)}\n"),
        "version": f"version: {scalar(facts['version'])}\n",
        "date-released": f"date-released: {quoted(facts['date'])}\n",
    }
    expected = {
        "doi": concept,
        "identifiers": [{"description": CONCEPT_TEXT, "type": "doi", "value": concept},
                        {"description": version_text, "type": "doi", "value": version_doi}],
        "version": facts["version"],
        "date-released": facts["date"],
    }
    return blocks, expected


def segments(text):
    """[(key or None, text)]: the file split into top-level key blocks and the text between them.

    A block runs from its key line through the indented and blank lines that follow, minus trailing blank
    lines, so comments and spacing between keys are kept where they are."""
    lines = text.splitlines(keepends=True)
    parts, i = [], 0
    while i < len(lines):
        match = TOP_KEY.match(lines[i])
        if not match:
            parts.append((None, lines[i]))
            i += 1
            continue
        j = i + 1
        while j < len(lines) and (lines[j].strip() == "" or lines[j][0] in " \t"):
            j += 1
        end = j
        while end > i + 1 and lines[end - 1].strip() == "":
            end -= 1
        parts.append((match.group(1), "".join(lines[i:end])))
        parts.extend((None, line) for line in lines[end:j])
        i = j
    return parts


def rewrite_citation(text, facts, replace_concept, problems, notes):
    """The new text of CITATION.cff, or None when it must not be written."""
    try:
        old = yaml.safe_load(text)
    except yaml.YAMLError as error:
        problems.append(f"::error file=CITATION.cff::not valid YAML: {str(error).splitlines()[0]}")
        return None
    if not isinstance(old, dict) or "authors" not in old:
        problems.append("::error file=CITATION.cff::does not look like a citation file (no top-level authors key)")
        return None
    current = old.get("doi")
    if current and str(current) != facts["concept"]:
        message = (f"the Zenodo record for release {facts['tag']} is under concept DOI {facts['concept']}, but the primary "
                   f"doi here is {current}. A repository has one concept DOI, so Zenodo filed this release under a new "
                   "record (or the integration was recreated); look into it")
        if not replace_concept:
            problems.append(f"::error file=CITATION.cff::{message} before passing --replace-concept-doi")
            return None
        notes.append(f"::warning file=CITATION.cff::{message}. Replacing it as asked (--replace-concept-doi)")
    if isinstance(old.get("identifiers"), list):
        dropped = [i for i in old["identifiers"] if not (isinstance(i, dict) and i.get("type") == "doi")]
        if dropped:
            notes.append(f"::warning file=CITATION.cff::identifiers that are not DOIs are dropped; the list holds "
                         f"the concept and version DOI only: {dropped!r}")

    blocks, expected = render(facts)
    parts = [(key, blocks[key] if key in blocks else body) for key, body in segments(text)]
    keys = lambda: [key for key, _ in parts]

    def insert_before(key, anchors):
        for anchor in anchors:
            if anchor in keys():
                parts.insert(keys().index(anchor), (key, blocks[key]))
                return
        if parts and not parts[-1][1].endswith("\n"):
            parts.append((None, "\n"))
        parts.append((key, blocks[key]))

    def insert_after(key, anchor):
        parts.insert(keys().index(anchor) + 1, (key, blocks[key]))

    if "doi" not in keys():
        insert_before("doi", ["identifiers", "version", "date-released"])
    if "identifiers" not in keys():
        insert_after("identifiers", "doi")
    if "version" not in keys():
        insert_before("version", ["date-released"])
    if "date-released" not in keys():
        insert_after("date-released", "version")
    new = "".join(body for _, body in parts)

    try:
        parsed = yaml.safe_load(new)
    except yaml.YAMLError as error:
        problems.append(f"::error file=CITATION.cff::rewritten file is not valid YAML: {str(error).splitlines()[0]}")
        return None
    unmanaged = lambda data: {key: value for key, value in data.items() if key not in MANAGED_KEYS}
    if not isinstance(parsed, dict) or any(parsed.get(key) != value for key, value in expected.items()) \
            or unmanaged(parsed) != unmanaged(old):
        problems.append("::error file=CITATION.cff::the rewritten file does not read back as intended; nothing written")
        return None
    return new


def rewrite_readme(text, concept, rel, notes):
    """README text with the concept-DOI badge under its first heading; unchanged when it already has a badge."""
    if "zenodo.org/badge/DOI/" in text:
        return text
    badge = BADGE.format(doi=concept) + "\n"
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("# "):
            if i + 1 < len(lines) and lines[i + 1].strip() == "":
                lines.insert(i + 2, badge + "\n")
            else:
                lines.insert(i + 1, "\n" + badge + "\n")
            return "".join(lines)
    notes.append(f"::warning file={rel}::no top-level heading to put the DOI badge under; left as it is")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", help="the release tag, exactly as published (1.0.0 or v1.0.0)")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"), help="OWNER/REPO (default: $GITHUB_REPOSITORY)")
    parser.add_argument("--api", default=DEFAULT_API, help=f"Zenodo API base (default {DEFAULT_API})")
    parser.add_argument("--wait", action="store_true", help="poll until the record exists or --timeout is spent")
    parser.add_argument("--timeout", type=int, default=2700, help="seconds to keep polling with --wait (default 2700)")
    parser.add_argument("--interval", type=int, default=60, help="seconds between polls (default 60)")
    parser.add_argument("--version-doi", help="offline mode: the version DOI to record")
    parser.add_argument("--concept-doi", help="offline mode: the concept DOI to record")
    parser.add_argument("--date-released", help="offline mode: the release date, YYYY-MM-DD")
    parser.add_argument("--replace-concept-doi", action="store_true", help="allow the primary doi to change")
    parser.add_argument("--badge", type=Path, help="README file to add the concept-DOI badge to, e.g. README.md")
    parser.add_argument("--check", action="store_true", help="exit 1 when a file would change; write nothing")
    args = parser.parse_args()

    overrides = {"concept": args.concept_doi, "version_doi": args.version_doi, "date": args.date_released}
    if any(overrides.values()) and not all(overrides.values()):
        parser.error("--version-doi, --concept-doi and --date-released go together (offline mode)")
    if not all(overrides.values()) and not args.repo:
        parser.error("--repo OWNER/REPO is required when GITHUB_REPOSITORY is not set")
    if args.interval < 1 or args.timeout < 1:
        parser.error("--interval and --timeout must be positive")

    try:
        if all(overrides.values()):
            facts = release_facts(args.tag, overrides=overrides)
        else:
            api = args.api.rstrip("/")
            record = wait_for_record(api, args.repo, args.tag, args.wait, args.timeout, args.interval)
            if record is None:
                budget = f"{args.timeout // 60} min" if args.timeout >= 120 else f"{args.timeout} s"
                waited = f" after {budget}" if args.wait else ""
                print(f"::error file=CITATION.cff::Zenodo has no record for {tree_url(args.repo, args.tag)}{waited}. "
                      "Check https://zenodo.org/account/settings/github/ for a failed release (an invalid CITATION.cff "
                      "is the usual cause; the switch for this repository must be on). Once a record exists, re-run: "
                      f"gh workflow run zenodo-doi.yml -f tag={args.tag}")
                return 1
            facts = release_facts(args.tag, record=record)
    except Fatal as error:
        print(f"::error::{error}")
        return 1

    problems, notes, changes = [], [], []
    try:
        text = CITATION_FILE.read_text()
    except OSError as error:
        sys.exit(f"sync-release-doi: cannot read {CITATION_FILE}: {error}")
    new = rewrite_citation(text, facts, args.replace_concept_doi, problems, notes)
    if new is not None and new != text:
        changes.append((CITATION_FILE, text, new))
    if args.badge:
        readme = args.badge if args.badge.is_absolute() else ROOT / args.badge
        rel = readme.relative_to(ROOT).as_posix() if readme.is_relative_to(ROOT) else str(readme)
        try:
            old_readme = readme.read_text()
        except OSError as error:
            problems.append(f"::error file={rel}::cannot read it for the DOI badge: {error}")
        else:
            new_readme = rewrite_readme(old_readme, facts["concept"], rel, notes)
            if new_readme != old_readme:
                changes.append((readme, old_readme, new_readme))

    for message in notes + problems:
        print(message)
    if problems:
        print(f"sync-release-doi: {len(problems)} problem(s) to fix by hand; nothing written")
        return 1
    if not changes:
        print(f"sync-release-doi: CITATION.cff already records release {args.tag} "
              f"(version DOI {facts['version_doi']} under concept DOI {facts['concept']})")
        return 0
    if args.check:
        for path, old, updated in changes:
            rel = path.relative_to(ROOT).as_posix()
            print(f"::error file={rel}::out of date for release {args.tag}; run python3 .github/scripts/sync-release-doi.py "
                  f"{args.tag} and commit the result")
            print("".join(difflib.unified_diff(old.splitlines(True), updated.splitlines(True), rel, rel + " (synced)")))
        return 1
    for path, _, updated in changes:
        path.write_text(updated)
        print(f"rewrote {path.relative_to(ROOT).as_posix()}")
    print(f"::notice file=CITATION.cff::recorded release {args.tag}: version DOI {facts['version_doi']} "
          f"under concept DOI {facts['concept']}, released {facts['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
