#!/usr/bin/env python3
"""Keep the author list in CITATION.cff in step with the people credited on the cookbook's pages.

The cookbook's authors are the people credited in the `authors:` frontmatter of its pages, which in practice
means the chapter pages under 01-.../, 02-.../ and so on. This script collects them, looks each one up in
authors.yml (the ground truth for names, ORCIDs and affiliations) and rewrites the `authors:` list in
CITATION.cff to match. Adding a chapter with a new author adds that person to the citation; removing the last
chapter a person worked on removes them. Nothing else in CITATION.cff is touched.

  CITATION.cff                          authors.yml                        02-.../02.1-Introduction.md
  authors:                              contributors:                      authors:
    - family-names: Lombardi    <---      - id: rachel_lombardi    <---      - name: Rachel Lombardi
      given-names: Rachel                   name: Rachel Lombardi              orcid: 0000-0001-8917-3810
      orcid: "https://orcid.org/..."        orcid: 0000-0001-8917-3810         roles: [...]
      affiliation: "Center for ..."         affiliations: [CHTC]

Order: people are listed in the order authors.yml lists them, so the citation order is decided there. Someone
credited on a page but missing from authors.yml is appended after them in order of first appearance, with a
warning, because their name then has to be split without help. Each CFF author gets family-names (the last
word of the name), given-names (the rest), the ORCID as a URL and affiliation (the names of their authors.yml
affiliations, joined with '; '). A page author is matched to authors.yml by contributor id (the short form
`- id: rachel_lombardi`), else by ORCID, else by name.

Usage:
  sync-citation.py            rewrite CITATION.cff when its author list is out of date (exit 0)
  sync-citation.py --check    change nothing; exit 1 with a diff when CITATION.cff would be rewritten

Both modes exit 1, and write nothing, on a problem that could leave someone out: a page whose frontmatter
cannot be read (a bare-id author entry needs sync-page-authors.py first), an author id or affiliation id that
authors.yml does not define, no page crediting anyone, or a CITATION.cff without a top-level `authors:` list.
A person in authors.yml who is credited on no page is reported as a notice and left out of the citation.
Run from anywhere inside the cookbook; the files are found next to the .github directory. README.md,
dot-directories, _build and node_modules are skipped. Requires PyYAML.
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
AUTHORS_FILE = ROOT / "authors.yml"
CITATION_FILE = ROOT / "CITATION.cff"
ORCID = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")


def normalize(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def orcid_id(value):
    """'0000-0001-7113-3685' from a bare or URL-form ORCID, or None when the value is not one."""
    text = re.sub(r"^HTTPS?://ORCID\.ORG/", "", str(value or "").strip().upper())
    return text if ORCID.fullmatch(text) else None


def affiliation_ids(value):
    """['CHTC', ...] from a MyST affiliations value (list of ids, names, or {id, name} objects)."""
    if not value:
        return []
    ids = []
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, dict):
            item = item.get("id") or item.get("name")
        if isinstance(item, str):
            ids.append(item)
    return ids


def load_people(problems):
    """authors.yml contributors in file order, plus lookups by id, by ORCID, by normalized name, and affiliation names by id."""
    try:
        config = yaml.safe_load(AUTHORS_FILE.read_text()) or {}
    except (OSError, yaml.YAMLError) as error:
        sys.exit(f"sync-citation: cannot read {AUTHORS_FILE}: {error}")
    project = config.get("project") or {}
    file = AUTHORS_FILE.relative_to(ROOT).as_posix()
    affiliations = {}
    for entry in project.get("affiliations") or []:
        if isinstance(entry, dict) and entry.get("id"):
            affiliations[entry["id"]] = str(entry.get("name") or entry.get("institution") or entry["id"])
    people, by_id, by_orcid, by_name = [], {}, {}, {}
    for entry in (project.get("contributors") or []) + (project.get("authors") or []):
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("name"):
            problems.append(f"::error file={file}::a contributor record needs both an id and a name: {entry!r}")
            continue
        label = entry["id"]
        names = []
        for aff in affiliation_ids(entry.get("affiliations") or entry.get("affiliation")):
            if aff in affiliations:
                names.append(affiliations[aff])
            else:
                problems.append(f"::error file={file}::'{label}' uses affiliation id '{aff}', which this file does not define")
        orcid = orcid_id(entry.get("orcid")) if entry.get("orcid") else None
        if entry.get("orcid") and not orcid:
            problems.append(f"::error file={file}::'{label}' has an invalid ORCID '{entry['orcid']}' (expected 0000-0000-0000-0000)")
        person = {"id": label, "name": str(entry["name"]), "orcid": orcid, "affiliations": names}
        people.append(person)
        by_id[label] = person
        if orcid:
            by_orcid.setdefault(orcid, person)
        by_name.setdefault(normalize(person["name"]), person)
    return people, {"id": by_id, "orcid": by_orcid, "name": by_name, "affiliations": affiliations}


def pages():
    skipped = lambda part: part.startswith(".") or part in ("_build", "node_modules")
    return [p for p in sorted(ROOT.rglob("*.md"))
            if p.name != "README.md" and not any(skipped(part) for part in p.relative_to(ROOT).parts)]


def page_authors(page, rel, problems):
    """The entries of a page's `authors:` frontmatter list, parsed, or [] when the page has none."""
    text = page.read_text()
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end < 0:
        return []
    try:
        frontmatter = yaml.safe_load(text[3:end])
    except yaml.YAMLError as error:
        problems.append(f"::error file={rel}::cannot read the frontmatter ({str(error).splitlines()[0]}); "
                        "an author written as a bare id needs python3 .github/scripts/sync-page-authors.py first")
        return []
    if not isinstance(frontmatter, dict) or frontmatter.get("authors") is None:
        return []
    authors = frontmatter["authors"]
    if not isinstance(authors, list):
        problems.append(f"::error file={rel}::'authors:' is not a list")
        return []
    return authors


def resolve(entry, lookups, rel, problems, notes):
    """The authors.yml person a page author entry credits, or a person built from the entry itself; None on error."""
    if isinstance(entry, str):
        if entry in lookups["id"]:
            return lookups["id"][entry]
        entry = {"name": entry}
    if not isinstance(entry, dict):
        problems.append(f"::error file={rel}::an author entry is neither a name nor a mapping: {entry!r}")
        return None
    if entry.get("id") and not entry.get("name"):
        person = lookups["id"].get(str(entry["id"]))
        if person is None:
            problems.append(f"::error file={rel}::author id '{entry['id']}' is not defined in authors.yml")
        return person
    orcid = orcid_id(entry.get("orcid")) if entry.get("orcid") else None
    person = lookups["orcid"].get(orcid) if orcid else None
    if person is None:
        person = lookups["name"].get(normalize(entry.get("name")))
    if person is not None:
        return person
    name = str(entry.get("name") or "").strip()
    if not name:
        problems.append(f"::error file={rel}::an author entry has neither a name nor an id: {entry!r}")
        return None
    notes.append(f"::warning file={rel}::'{name}' is not in authors.yml; cited with a best-guess name split. "
                 "Add them to authors.yml to control how they are cited")
    affiliations = [lookups["affiliations"].get(aff, aff)
                    for aff in affiliation_ids(entry.get("affiliations") or entry.get("affiliation"))]
    return {"id": None, "name": name, "orcid": orcid, "affiliations": affiliations}


def cff_author(person, notes):
    """The CFF person object for someone, as an ordered dict of the keys CITATION.cff should carry."""
    words = person["name"].split()
    author = {}
    if len(words) > 1:
        author["family-names"] = words[-1]
        author["given-names"] = " ".join(words[:-1])
    else:
        author["family-names"] = person["name"]
        notes.append(f"::warning file=CITATION.cff::'{person['name']}' is a single word; cited as a family name only")
    if person["orcid"]:
        author["orcid"] = "https://orcid.org/" + person["orcid"]
    if person["affiliations"]:
        author["affiliation"] = "; ".join(person["affiliations"])
    return author


def scalar(value):
    """A YAML scalar in CITATION.cff's house style: plain when it is simple text that YAML reads back unchanged, else double-quoted."""
    value = str(value)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .'()\-]*[A-Za-z0-9.)]", value) and yaml.safe_load(value) == value:
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(authors):
    """The text of the `authors:` block (the lines under the key) for a list of CFF person objects."""
    lines = []
    for author in authors:
        prefix = "  - "
        for key, value in author.items():
            lines.append(f"{prefix}{key}: {scalar(value)}\n")
            prefix = "    "
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when CITATION.cff would change; write nothing")
    args = parser.parse_args()

    problems, notes = [], []
    people, lookups = load_people(problems)
    credited = {}                                      # key -> person, in order of first appearance
    for page in pages():
        rel = page.relative_to(ROOT).as_posix()
        for entry in page_authors(page, rel, problems):
            person = resolve(entry, lookups, rel, problems, notes)
            if person is not None:
                credited.setdefault(person["id"] or person["orcid"] or normalize(person["name"]), person)
    for person in people:
        if person["id"] not in credited:
            notes.append(f"::notice file=authors.yml::'{person['id']}' is credited on no page, so CITATION.cff does not list them")
    ordered = [p for p in people if p["id"] in credited] + [p for p in credited.values() if p["id"] is None]
    if not ordered and not problems:
        problems.append("::error file=CITATION.cff::no page credits an author; refusing to empty the author list")
    authors = [cff_author(person, notes) for person in ordered]

    try:
        text = CITATION_FILE.read_text()
    except OSError as error:
        sys.exit(f"sync-citation: cannot read {CITATION_FILE}: {error}")
    key = re.search(r"^authors:[ \t]*\n", text, re.M)
    new = None
    if not key:
        problems.append("::error file=CITATION.cff::no top-level 'authors:' list to rewrite")
    elif not problems:
        following = re.compile(r"^\S", re.M).search(text, key.end())
        end = following.start() if following else len(text)
        new = text[:key.end()] + render(authors) + text[end:]
        try:
            if yaml.safe_load(new).get("authors") != authors:
                problems.append("::error file=CITATION.cff::the rewritten author list does not read back as intended")
        except yaml.YAMLError as error:
            problems.append(f"::error file=CITATION.cff::rewritten file is not valid YAML: {str(error).splitlines()[0]}")

    for message in notes + problems:
        print(message)
    if problems:
        print(f"sync-citation: {len(problems)} problem(s) to fix by hand; CITATION.cff left as it is")
        return 1
    if new == text:
        print(f"sync-citation: CITATION.cff already lists the {len(authors)} author(s) credited on the pages")
        return 0
    if args.check:
        print("::error file=CITATION.cff::the author list is out of date; run python3 .github/scripts/sync-citation.py and commit the result")
        print("".join(difflib.unified_diff(text.splitlines(True), new.splitlines(True), "CITATION.cff", "CITATION.cff (synced)")))
        return 1
    CITATION_FILE.write_text(new)
    print(f"sync-citation: rewrote CITATION.cff with the {len(authors)} author(s) credited on the pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
