#!/usr/bin/env bash
# Fail the build when placeholder text, personal paths, or non-MyST syntax slips into a page.
# Runs over every Markdown page in the repository (submodules included), skipping build output.
set -uo pipefail
cd "$(dirname "$0")/../.."

# Fixed strings that must never appear in published pages.
fixed=(
  'damorales4'
  'XXXXXX'
  'WORK IN PROGRESS'
  'NEEDS TO BE DONE'
  '(link here)'
  ']()'
  'no-such-block'
  'Internal page'
  '@ap40 '
  '<user.name>'
  '<username>'
  'ap####'
  'ap200x'
)
# Regular expressions (extended syntax).
regex=(
  '^> \[!(TIP|NOTE|WARNING|IMPORTANT|CAUTION)\]'   # GitHub alert syntax; use :::{tip} directives
  '^\s*TODO\b'
)

status=0
while IFS= read -r -d '' file; do
  for p in "${fixed[@]}"; do
    if grep -nF -- "$p" "$file" >/dev/null; then
      echo "::error file=${file}::forbidden text: ${p}"
      grep -nF -- "$p" "$file" | head -3
      status=1
    fi
  done
  for p in "${regex[@]}"; do
    if grep -nE -- "$p" "$file" >/dev/null; then
      echo "::error file=${file}::forbidden pattern: ${p}"
      grep -nE -- "$p" "$file" | head -3
      status=1
    fi
  done
done < <(find . -type f -name '*.md' -not -path '*/_build/*' -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/.github/*' -print0)

if [ "$status" -eq 0 ]; then echo "lint-content: OK"; fi
exit "$status"
