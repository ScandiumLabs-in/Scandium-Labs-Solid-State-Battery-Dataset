# We Built a Solid-State Battery Electrolyte Dataset Because the Good Data Doesn't Exist Yet

If you've tried to train a model to predict ionic conductivity in solid-state electrolytes, you already know the problem. Materials Project, JARVIS-DFT, OQMD: these give you hundreds of thousands of crystal structures and DFT-computed properties. What they don't give you is the number you actually want: how well lithium moves through the material at room temperature.

That number comes from an experiment, buried in a PDF, usually in a table three sections after the abstract.

So we built a dataset around that number instead of around structure counts.

**The dataset:** [solid-state-electrolyte-conductivity](https://huggingface.co/datasets/Scandium-Labs/solid-state-electrolyte-conductivity), released by Scandium Labs on Hugging Face.

## What's Actually in It

The release has two parts, and they matter for different reasons.

The first part is **30,838 bulk structural and thermodynamic DFT records** pulled from Materials Project, JARVIS-DFT, COD, AFLOW, NOMAD, and OQMD. This is the composition and structure backbone: lattice parameters, space groups, formation energy, band gap, coordination environments, and the features you'd feed into a graph neural network or a composition-based model.

The second part is smaller and, honestly, the part we actually care about: **183 human-verified experimental conductivity and activation energy labels**, each one traced back to its source paper, page number, and the specific sentence it was pulled from.

On top of that sit **427 materials with cross-paper consensus statistics** — multiple papers reporting on the same composition, checked against each other — and a **165-record gold benchmark** for evaluation.

**183 out of 31,000 is not a typo. It's the point.**

Anyone can scrape structures. Verified, source-traceable transport-property labels are the scarce resource in this field, and that scarcity is exactly why models trained only on structural proxies tend to disappoint once you check them against real conductivity measurements.

## How the Labels Got Verified

We didn't hand-label 183 numbers and call it a day.

The pipeline runs eight source connectors for ingestion, classifies materials into their solid-state electrolyte family, mines the literature with LLM-assisted extraction, and then runs deterministic checks:

- Arrhenius consistency
- Unit normalization
- Cross-paper agreement
- Source and metadata validation

Records that pass go through human review before they're scored and released.

One detail worth calling out for anyone planning to build on this:

> Once ingestion is done, the pipeline is fully deterministic. No LLM calls are needed to reproduce any artifact in the release.

The extraction step uses an LLM; the verification step doesn't rely on one.

## Coverage Across Electrolyte Families

All 11 major solid-state electrolyte families are represented:

- Sulfides
- Oxides
- Garnets
- Perovskites
- NASICONs
- Halides
- Argyrodites
- Hydrides
- Borohydrides
- Antiperovskites
- Polymer or composite systems

That said, coverage isn't even, and we'd rather say so than let someone find out the hard way.

Sulfides and garnets dominate the verified labels because that's where most of the published experimental work sits. Antiperovskites, hydrides, and borohydrides are thinner, and that's a reflection of publication volume in the field, not a sampling decision we made.

## What We're Not Claiming

**98% of the quality-scored records land in a single "silver" tier.**

That's not a scoring bug. It's what happens when experimental metadata such as density, pressure, and atmosphere is sparse across the source papers.

We'd rather show that honestly than round the scores up.

The bulk DFT rows also aren't pre-screened for electrolyte relevance, so if you're pulling from that portion, check the family tags and negative flags before you use them.

And **150 AFLOW rows carry a non-commercial restriction** from their source license, which is called out in the license breakdown file rather than buried.

## Splits That Won't Leak

Train and test splits are grouped by composition-family key, so polymorphs and doped variants of the same base composition don't end up split across train and test.

If you've trained a materials property model before, you know how easily that kind of leakage inflates a benchmark number without anyone noticing until deployment.

A model can look excellent on a random split while effectively seeing the same chemistry during training and testing.

We wanted the evaluation to be harder — and more representative of what happens when the model encounters genuinely different materials.

## Where It Fits With Our Other Release

This dataset pairs with our earlier release, the [Scandium Dataset](https://huggingface.co/Scandium-Labs), a harmonized DFT structural and thermodynamic screening set covering **267,230 materials** from Materials Project, OQMD, and JARVIS-DFT.

That dataset is built for the early discovery stage: narrowing a huge structural search space down to plausible candidates.

This new release picks up from there, adding the transport-property labels needed to actually rank those candidates by how well lithium moves through them.

In simple terms:

**Scandium Dataset**

> Large-scale structural and thermodynamic screening

↓

**Solid-State Electrolyte Conductivity Dataset**

> Experimental transport-property validation

↓

**Candidate ranking and discovery**

The goal is to connect computational screening with experimentally observed electrolyte performance.

## Why This Matters for Solid-State Batteries

Ionic conductivity at room temperature is one of the practical bottlenecks standing between solid-state electrolyte research and a battery you could put in a car.

A model can screen a hundred thousand candidate structures in an afternoon, but it can only screen well if it was trained against real transport measurements rather than a structural proxy that correlates loosely, if at all, with conductivity.

That's the gap this dataset is aimed at closing.

The problem isn't a lack of structures.

The problem is a lack of **reliable, experimentally grounded transport-property data** connected to those structures.

## Get the Data

The dataset is live on Hugging Face under a **CC-BY-4.0 license for Scandium-authored content**. Third-party records retain their original source licenses, which are detailed in the license breakdown file.

**Dataset:**  
[https://huggingface.co/datasets/Scandium-Labs/solid-state-electrolyte-conductivity](https://huggingface.co/datasets/Scandium-Labs/solid-state-electrolyte-conductivity)

Pipeline source code and the issue tracker are available on [GitHub](https://github.com/ScandiumLabs-in).

If you find an error in a label or want to submit a correction, that's the place to open an issue.

---

*Scandium Labs is building physics-informed graph neural networks for solid-state battery electrolyte discovery. This dataset is part of that work, released for anyone else trying to solve the same transport-property bottleneck.*

## Suggested Medium Tags

**Materials Science, Battery Technology, Machine Learning, Open Data, Solid-State Batteries**
