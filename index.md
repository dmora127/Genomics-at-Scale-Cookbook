---
title: Genomics at Scale Cookbook
subtitle: Recipes for running genomics workflows at scale on CHTC
short_title: Genomics at Scale
---

The **Genomics at Scale Cookbook** collects step-by-step recipes for running genomics workflows on the [Center for High Throughput Computing (CHTC)](https://chtc.cs.wisc.edu) system. Each recipe is a complete workflow that has been run on CHTC: it comes with HTCondor submit files, an Apptainer container definition, a toy dataset, and guidance on resource requests, data movement, and failure modes.

The recipes are written for researchers who already know *what* analysis they want to run and need to know *how* to run it as hundreds or thousands of jobs. They are not an introduction to genomics.

## Recipes

:::{card} Basecalling Nanopore Data with Dorado on CHTC GPUs
:link: ./01-Basecalling-GPUs/01.1-Introduction.md

Split raw Oxford Nanopore POD5 files by sequencing channel and basecall them as hundreds of independent GPU jobs with Dorado. Covers building the container, staging basecalling models, preprocessing the data, submitting and monitoring the jobs, and merging the results.
:::

:::{card} Assessing Read Quality with FastQC on CHTC
:link: ./02-Quality-with-FASTQC/02.1-Introduction.md

Run FastQC on one FASTQ file, then on every file with a single submit file and the `queue ... from` syntax. The smallest recipe in the cookbook, and the clearest introduction to the one-job-per-sample pattern the others rely on. Ends with a MultiQC summary job.
:::

:::{card} Mapping Long Reads with Minimap2 on CHTC
:link: ./03-Read-Mapping-with-Minimap2/03.1-Introduction.md

Index a reference genome once, split a Nanopore read set into chunks, and map the chunks as hundreds of parallel Minimap2 jobs that return sorted BAM files. Covers which files belong in `/staging` and travel through OSDF, and which belong in `/home`.
:::

:::{card} Assembling a Genome from Nanopore Reads with hifiasm on CHTC
:link: ./04-Genome-Assembly-with-HiFiAsm/04.1-Introduction.md

Assemble a 2.4 Gb mammalian genome from 318 GB of Nanopore reads in one high-memory hifiasm job. Covers staging very large inputs with Pelican, reading them in place from `/staging`, sizing CPU, memory, and disk requests, and interpreting hifiasm's haplotype-resolved output.
:::

See [how to contribute](https://dmora127.github.io/chtc-biocafe-cookbook/frontmatter/contribute) if you have a workflow to share.

## Before You Start

Every recipe assumes that you:

* Have a CHTC HTC account and can log into an Access Point (for example `ap2001.chtc.wisc.edu`). Request an account through the [CHTC account request form](https://chtc.cs.wisc.edu/uw-research-computing/form.html).
* Have a `/staging` directory for large files (every recipe except FastQC needs one). Request one through the [CHTC large data guide](https://chtc.cs.wisc.edu/uw-research-computing/file-avail-largedata).
* Can submit and monitor HTCondor jobs. If you are new to HTCondor, complete the [Roadmap to getting started](https://chtc.cs.wisc.edu/uw-research-computing/htc-roadmap) first.
* Are comfortable on the Linux command line.

## Companion Repositories

The executables, submit files, and container definitions used by each recipe live in a companion GitHub repository that you clone onto the Access Point:

| Recipe | Repository |
|--------|------------|
| Basecalling with Dorado | [tutorial-ONT-Basecalling](https://github.com/dmora127/tutorial-ONT-Basecalling) |
| Read quality with FastQC | [tutorial-fastqc](https://github.com/CHTC/tutorial-fastqc) |
| Read mapping with Minimap2 | [CHTC-BioCafe-Fall25-Minimap2](https://github.com/dmora127/CHTC-BioCafe-Fall25-Minimap2) |
| Genome assembly with hifiasm | [tutorial-CHTC-Genome-Assembly](https://github.com/CHTC/tutorial-CHTC-Genome-Assembly) |

## How to Cite

If this cookbook helped your research, please cite it. A citation file (`CITATION.cff`) is included in the repository, and a DOI is minted for each published release.

% Generated from CITATION.cff by .github/scripts/sync-index-citation.py on every push. Change CITATION.cff or authors.yml, not this quote.

> Morales, D. A., Lombardi, R., & Koch, C. (2026). *Genomics at Scale Cookbook* (Version 1.0.0). Center for High Throughput Computing, University of Wisconsin-Madison. https://github.com/dmora127/Genomics-at-Scale-Cookbook

## Part of the CHTC Bioinformatics Cookbooks

This cookbook is one volume of the [CHTC Bioinformatics Cookbooks](https://dmora127.github.io/chtc-biocafe-cookbook/), which also include conceptual chapters on high-throughput computing for bioinformatics and the [Proteins at Scale Cookbook](https://github.com/dmora127/Proteins-at-Scale-Cookbook). Content is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
