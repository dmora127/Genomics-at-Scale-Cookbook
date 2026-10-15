# Genomics at Scale Cookbook

Recipes for running genomics workflows at scale on the [Center for High Throughput Computing (CHTC)](https://chtc.cs.wisc.edu) system. Part of the [CHTC Bioinformatics Cookbooks](https://dmora127.github.io/chtc-biocafe-cookbook/).

## Recipes

| Recipe | Directory | Companion repository |
|--------|-----------|----------------------|
| Basecalling Nanopore Data with Dorado on CHTC GPUs | `01-Basecalling-GPUs/` | [tutorial-ONT-Basecalling](https://github.com/dmora127/tutorial-ONT-Basecalling) |
| Assessing Read Quality with FastQC on CHTC | `02-Quality-with-FASTQC/` | [tutorial-fastqc](https://github.com/CHTC/tutorial-fastqc) |
| Mapping Long Reads with Minimap2 on CHTC | `03-Read-Mapping-with-Minimap2/` | [CHTC-BioCafe-Fall25-Minimap2](https://github.com/dmora127/CHTC-BioCafe-Fall25-Minimap2) |
| Assembling a Genome from Nanopore Reads with hifiasm on CHTC | `04-Genome-Assembly-with-HiFiAsm/` | [tutorial-CHTC-Genome-Assembly](https://github.com/CHTC/tutorial-CHTC-Genome-Assembly) |

Each recipe is a chapter of MyST Markdown pages. The executables, submit files, and container definitions it uses live in the companion repository, which readers clone onto a CHTC Access Point.

## Preview locally

The cookbook is built with [MyST](https://mystmd.org).

```bash
npm install -g mystmd      # or: pip install mystmd
cp myst.standalone.yml myst.yml
myst start                 # serves the cookbook at http://localhost:3000
```

The configuration lives in `myst.standalone.yml` rather than `myst.yml` on purpose: the hub site includes this repository as a git submodule, and a committed `myst.yml` would be detected by the hub build as a second project. `myst.yml` is in `.gitignore`, so the local copy is never committed.

`myst build --html` writes a static site to `_build/html/`. The `Build cookbook` workflow runs the same build, plus `.github/scripts/lint-content.sh`, on every push and pull request.

## Repository layout

```
.
├── myst.standalone.yml                 # project metadata, table of contents, site options (copied to myst.yml for standalone builds)
├── index.md                            # cookbook landing page
├── 01-Basecalling-GPUs/                # one directory per recipe; pages numbered 01.1, 01.2, ...
├── 02-Quality-with-FASTQC/
├── 03-Read-Mapping-with-Minimap2/
├── 04-Genome-Assembly-with-HiFiAsm/
├── .images/                            # figures used by the pages (photos carry their attribution in the page caption)
├── CITATION.cff
├── LICENSE                             # CC BY 4.0
└── .github/                            # CI workflows and the content lint script
```

## Contributing

Fixes and improvements are welcome as pull requests. New recipes should follow the layout above and the conventions described in the [contributing guide](https://dmora127.github.io/chtc-biocafe-cookbook/frontmatter/contribute) of the CHTC Bioinformatics Cookbooks. Questions: chtc@cs.wisc.edu.

## Citation and license

See `CITATION.cff`. Content is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
