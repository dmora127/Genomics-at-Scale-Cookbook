#!/usr/bin/env python3
"""Keep the author entries in page frontmatter in step with authors.yml.

Pages credit people as full inline author objects, because MyST cannot attach per-page roles to a contributor
referenced by id. This script lets authors write the short form and keeps the long form correct:

  authors:                        authors:
    - id: rachel_lombardi           - name: Rachel Lombardi
      roles:               --->       orcid: 0000-0001-8917-3810
        - Conceptualization            affiliations:
                                         - CHTC
                                       roles:
                                         - Conceptualization

A short entry is a contributor id from authors.yml (`- id: rachel_lombardi`, or the bare `- rachel_lombardi`,
which is not valid YAML once roles follow it) plus the page's own roles. It is expanded with the person's
name, ORCID and affiliations from authors.yml. An entry that already has a name is matched to authors.yml by
ORCID, or else by name, and its name, ORCID and affiliations are refreshed from there. Only those three keys
are ever rewritten: roles and any other keys stay exactly as the page has them. A person that authors.yml
does not know is left as written.

Usage:
  sync-page-authors.py            rewrite pages whose author entries are short or out of date (exit 0)
  sync-page-authors.py --check    change nothing; exit 1 with a diff when a page would be rewritten

Both modes also check authors.yml itself, since it is the ground truth for this cookbook's people and ORCID is
how people are identified across cookbooks: a record without an id or a name, an ORCID that is malformed or
fails its checksum, the same ORCID on two records, or an affiliation id the file does not define is an error;
a record without an ORCID is a warning. Both modes exit 1 on any error, including a page that names a
contributor id authors.yml does not define. Run from anywhere inside the cookbook; authors.yml is found next
to the .github directory. README.md, dot-directories, _build and node_modules are skipped. Requires PyYAML.
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
AUTHORS_FILE = ROOT / "authors.yml"
MANAGED_KEYS = ("name", "orcid", "affiliations", "affiliation")
KEY_LINE = re.compile(r"^    ([A-Za-z_][A-Za-z0-9_-]*):(?:\s|$)")   # a key directly under the list item
BARE_ID = re.compile(r"[A-Za-z0-9_.-]+")


def normalize(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


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


def orcid_checksum_ok(orcid):
    """ISO 7064 MOD 11-2: the last character of an ORCID checks the other fifteen digits."""
    digits = orcid.replace("-", "")
    total = 0
    for digit in digits[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ("X" if check == 10 else str(check))


def load_people(problems, notes):
    """Contributors defined in authors.yml, indexed by id, by ORCID, and by normalized name, after checking the file."""
    try:
        config = yaml.safe_load(AUTHORS_FILE.read_text()) or {}
    except (OSError, yaml.YAMLError) as error:
        sys.exit(f"sync-page-authors: cannot read {AUTHORS_FILE}: {error}")
    project = config.get("project") or {}
    file = AUTHORS_FILE.relative_to(ROOT).as_posix()
    defined = {entry.get("id") for entry in project.get("affiliations") or [] if isinstance(entry, dict)}
    by_id, by_orcid, by_name = {}, {}, {}
    for entry in (project.get("contributors") or []) + (project.get("authors") or []):
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("name"):
            problems.append(f"::error file={file}::a contributor record needs both an id and a name: {entry!r}")
            continue
        label = entry["id"]
        orcid = None
        if entry.get("orcid"):
            orcid = str(entry["orcid"]).strip().upper()
            if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid) or not orcid_checksum_ok(orcid):
                problems.append(f"::error file={file}::'{label}' has an invalid ORCID '{entry['orcid']}' (expected 0000-0000-0000-0000 with a valid checksum)")
                orcid = None
            elif orcid in by_orcid:
                problems.append(f"::error file={file}::ORCID {orcid} is on two records ('{by_orcid[orcid]['id']}' and '{label}'); merge them into one")
        else:
            notes.append(f"::warning file={file}::'{label}' has no ORCID; people are matched across cookbooks by ORCID")
        affiliations = affiliation_ids(entry.get("affiliations") or entry.get("affiliation"))
        for aff in affiliations:
            if aff not in defined:
                problems.append(f"::error file={file}::'{label}' uses affiliation id '{aff}', which this file does not define")
        person = {"id": label, "name": str(entry["name"]), "orcid": orcid, "affiliations": affiliations}
        by_id[label] = person
        if orcid and orcid not in by_orcid:
            by_orcid[orcid] = person
        by_name[normalize(person["name"])] = person
    return by_id, by_orcid, by_name


def scalar(value):
    """A YAML scalar in the pages' house style: plain when it is simple text, double-quoted otherwise."""
    value = str(value)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .'()\-]*[A-Za-z0-9.)]", value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def managed_lines(person):
    """The name, orcid and affiliations lines for a person, indented as keys of a list item."""
    lines = [f"    name: {scalar(person['name'])}\n"]
    if person["orcid"]:
        lines.append(f"    orcid: {person['orcid']}\n")
    if person["affiliations"]:
        lines.append("    affiliations:\n")
        lines.extend(f"      - {scalar(aff)}\n" for aff in person["affiliations"])
    return lines


def split_entries(block):
    """The text of an `authors:` block as one string per `  - ` list item, plus any text before the first."""
    entries, current = [], []
    for line in block.splitlines(keepends=True):
        if line.startswith("  - "):
            if current:
                entries.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append("".join(current))
    return entries


def key_groups(lines):
    """[(key or None, [lines])]: each key directly under the list item with its continuation lines."""
    groups = []
    for line in lines:
        match = KEY_LINE.match(line)
        if match:
            groups.append((match.group(1), [line]))
        elif groups:
            groups[-1][1].append(line)
        else:
            groups.append((None, [line]))
    return groups


def parse_entry(text):
    """(contributor id or None, attributes dict, key groups) for one list item, accepting the bare-id form."""
    lines = text.splitlines(keepends=True)
    head = lines[0][4:].rstrip("\n")
    if BARE_ID.fullmatch(head.strip()):                  # `  - rachel_lombardi`, maybe followed by roles
        groups = key_groups(lines[1:])
        attrs = yaml.safe_load("".join("".join(g[1]) for g in groups)) if len(lines) > 1 else {}
        if attrs is not None and not isinstance(attrs, dict):
            raise ValueError("expected keys under the author id")
        return head.strip(), dict(attrs or {}), groups
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, list) or len(loaded) != 1:
        raise ValueError("could not parse the author entry")
    item = loaded[0]
    if isinstance(item, str):                           # `  - Jane Doe`
        return None, {"name": item}, key_groups(["    " + lines[0][4:]] + lines[1:])
    if not isinstance(item, dict):
        raise ValueError("author entry is neither a name nor a mapping")
    groups = key_groups(["    " + lines[0][4:]] + lines[1:])
    if "id" in item and "name" not in item:
        return str(item["id"]), dict(item), groups
    return None, dict(item), groups


def find_person(contributor_id, attrs, people, rel, problems, notes):
    by_id, by_orcid, by_name = people
    if contributor_id is not None:
        person = by_id.get(contributor_id)
        if person is None:
            problems.append(f"::error file={rel}::author id '{contributor_id}' is not defined in authors.yml")
        return person
    orcid = attrs.get("orcid")
    person = by_orcid.get(str(orcid)) if orcid else None
    if person is None:
        person = by_name.get(normalize(attrs.get("name")))
    if person is None:
        notes.append(f"::notice file={rel}::'{attrs.get('name')}' is not in authors.yml; left as written")
    return person


def rebuild_entry(person, groups, compact):
    """The entry text with the managed keys regenerated and every other line kept as it was."""
    kept = [g for g in groups if g[0] not in MANAGED_KEYS and not (compact and g[0] == "id")]
    lines = managed_lines(person) + [line for _, group in kept for line in group]
    lines[0] = "  - " + lines[0][4:]
    return "".join(lines)


def sync_page(page, people, problems, notes):
    """(old frontmatter, new frontmatter, body) for a page, or None when it has no authors block to sync."""
    text = page.read_text()
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    frontmatter, body = text[:end] + "\n", text[end + 1:]
    key = re.search(r"^authors:(.*)\n", frontmatter, re.M)
    if not key:
        return None
    rel = page.relative_to(ROOT).as_posix()
    if key.group(1).strip():
        notes.append(f"::notice file={rel}::'authors:' is not a block list; left as written")
        return None
    start = key.end()
    rest = frontmatter[start:]
    following = re.search(r"^\S", rest, re.M)
    block = rest[:following.start()] if following else rest
    tail = rest[following.start():] if following else ""

    pieces = []
    for item in split_entries(block):
        if not item.startswith("  - "):
            pieces.append(item)                      # comments or blank lines before the first entry
            continue
        try:
            contributor_id, attrs, groups = parse_entry(item)
        except (yaml.YAMLError, ValueError) as error:
            problems.append(f"::error file={rel}::cannot parse an author entry: {str(error).splitlines()[0]}")
            pieces.append(item)
            continue
        person = find_person(contributor_id, attrs, people, rel, problems, notes)
        pieces.append(rebuild_entry(person, groups, contributor_id is not None) if person else item)
    new_frontmatter = frontmatter[:start] + "".join(pieces) + tail
    if new_frontmatter != frontmatter:
        try:
            yaml.safe_load(new_frontmatter)
        except yaml.YAMLError as error:
            problems.append(f"::error file={rel}::rewritten frontmatter is not valid YAML: {str(error).splitlines()[0]}")
            return None
    return frontmatter, new_frontmatter, body


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when a page would change; write nothing")
    parser.add_argument("paths", nargs="*", type=Path, help="pages or directories to process (default: the whole cookbook)")
    args = parser.parse_args()

    problems, notes, changed = [], [], []
    people = load_people(problems, notes)
    targets = []
    for path in args.paths or [ROOT]:
        targets.extend(sorted(path.rglob("*.md")) if path.is_dir() else [path])
    skipped = lambda part: part.startswith(".") or part in ("_build", "node_modules")
    pages = [p for p in targets if p.name != "README.md" and not any(skipped(part) for part in p.relative_to(ROOT).parts)]

    for page in pages:
        result = sync_page(page, people, problems, notes)
        if result is None:
            continue
        old, new, body = result
        if old == new:
            continue
        rel = page.relative_to(ROOT).as_posix()
        changed.append(rel)
        if args.check:
            print(f"::error file={rel}::author entries are out of date; run python3 .github/scripts/sync-page-authors.py and commit the result")
            print("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), rel, rel + " (synced)")))
        else:
            page.write_text(new + body)
            print(f"rewrote {rel}")

    for message in notes + problems:
        print(message)
    summary = []
    if changed:
        summary.append(f"{len(changed)} page(s) out of date" if args.check else f"rewrote {len(changed)} page(s)")
    if problems:
        summary.append(f"{len(problems)} problem(s) to fix by hand")
    print("sync-page-authors: " + ("; ".join(summary) if summary else f"all {len(pages)} page(s) are up to date"))
    return 1 if problems or (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
