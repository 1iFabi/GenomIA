# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

People in Chile who bought a GenomIA genetic test and come back to read their own results once the lab publishes them. Staff roles (reception, analyst, admin) use separate post-login surfaces. *(Inferred from the repository: routes, roles and seed accounts.)*

## Product Purpose

GenomIA sequences a client's sample and returns five result modules: Ancestría, Farmacogenética, Rasgos, Riesgo poligénico and Riesgo monogénico. Success is a client who understands what each module says about them, without drowning in it or being alarmed by it.

## Positioning

A local test, read in Spanish, with the five modules in one place and an assistant (Genomin) that explains terms. *(Inferred; confirm before using it as a claim.)*

## Capabilities and Constraints

- Results come from `/api/genoma/v1/results/` (`useLatestGenomicsResults`): `modules` keyed `global_ancestry`, `local_ancestry`, `pharmacogenetics`, `traits`, `polygenic_risk`, `monogenic_risk`, plus `variant_summary`. A 404 means no published results yet.
- Riesgo poligénico and Riesgo monogénico share `/dashboard/enfermedades` (anchors `#polygenic_risk`, `#monogenic_risk`).
- The PDF report is not available yet; the dashboard says so and never generates a demo PDF.

## Brand Commitments

- The assistant is called Genomin.
- The 3D glass helix from the login video (pre-rendered frames in `frontend/public/dna-login/`) is the product's signature image, chosen by the owner.

## Evidence on Hand

Real result data for the dev seed account `cliente.completo`. No testimonials, customers or benchmarks exist; never invent them.

## Product Principles

- Genetic data is sensitive (Chile, Ley 21.719): each role sees the minimum it needs, and summary surfaces never surface a delicate finding (monogenic results show only how many variants were reviewed).
- Explain before alarming: results sit behind a deliberate step into each module.
- One place, five modules, always in the same order.

## Accessibility & Inclusion

Keyboard operable, respects reduced motion, Spanish copy throughout.
