# Edit and load the synthetic variant catalog

Edit [`synthetic_variant_catalog_v1.json`](synthetic_variant_catalog_v1.json) to maintain fictional development examples. It is a standard Django JSON fixture, not an importer or a patient dataset.

| Model label | Records | Purpose |
| --- | ---: | --- |
| `genoma.datarelease` | 1 | Explicit synthetic demo release |
| `genoma.variant` | 8 | Three SNVs, two MNVs, two deletions, one insertion |
| `genoma.variantplacement` | 8 | One fictional placement per variant |
| `genoma.releasevariant` | 8 | Release membership and placement links |

All 25 records use stable UUID links. `GENOMIA-DEMO-v1` and `DEMO-CONTIG-A` through `DEMO-CONTIG-D` are invented, not real reference assemblies or chromosomes. Coordinates and alleles are illustrative, not biologically validated. There are no real rsIDs, VRS identifiers, annotations, gene/frequency claims, patient genotypes, analyses, or clinical results. This catalog does **not** populate client panels or perform genotype analysis.

## Load later: development database only

1. Select and independently verify an isolated **development** database in the project's Django configuration. Apply the project's current migrations through its normal development setup first.
2. From `backend/sequoh`, use the existing environment's Python interpreter for this standard Django command:

   ```text
   python manage.py loaddata genoma/fixtures/synthetic_variant_catalog_v1.json --database default
   ```

3. Expect `Installed 25 object(s) from 1 fixture(s)` for the unchanged catalog. Loading it twice keeps the same 1/8/8/8 catalog record counts, assuming no unrelated catalog records already exist.

**The command writes the configured `default` database.** Standard `loaddata` has no development-only guard: do not run it against production or an unverified database. No persistent import was performed when adding this file; regression loading uses the guarded runner's disposable `gdb_test_*` database only.

Re-reading stable primary keys updates the fixture records' fields, including fixed timestamps. It can overwrite local changes; it is **not** an arbitrary production-safe idempotent import. Changing UUIDs creates different records, and removing JSON entries does not delete previously loaded rows. Existing non-catalog rows are not part of this fixture.

## Edit existing examples

- Keep each `pk` and its UUID references unchanged when editing the same logical record.
- Keep `status: "synthetic"`, synthetic canonical names, and `metadata.synthetic: true` with `purpose: "development_catalog_example"` and `biologically_validated: false` on variants and placements.
- Keep `vrs_id`, `manifest_checksum`, and `frozen_at` null, and `normalized` false. Neither publication, integrity verification, nor biological normalization is claimed.
- Use invented contigs and the demo assembly. With `1-based-inclusive` coordinates, require `start_pos >= 1`, `end_pos >= start_pos`, and `end_pos - start_pos + 1 == len(reference_allele)`.
- SNVs have one REF and one different ALT base; MNVs have equal lengths greater than one. Deletions retain a left anchor (`AT -> A`, spanning both REF bases); insertions retain it (`G -> GTC`, spanning only the REF anchor). Use nonempty A/C/G/T strings. These are representation examples, not normalization validation.

## Add a variant, placement, and membership

Copy an existing example's three objects and retain the list's dependency order: release, variants, placements, then memberships.

1. Assign a new unique UUID to the variant `pk` and a different new UUID to the placement `pk`. Preserve existing UUIDs; never reuse them for a different example.
2. Set the placement's `fields.variant` to the new variant UUID. Match its assembly to the release and edit its fictional REF/ALT coordinates coherently.
3. Set the membership's `fields.release` to the release UUID, `fields.variant` to the new variant UUID, and `fields.placement` to the new placement UUID. Its composite `pk` must be **`[release UUID, variant UUID]` in that order**, matching those two fields. Leave `included_by_analysis` null.

There is one membership per release/variant pair. For another placement of the same variant, create only a new placement UUID and optionally change that membership's placement reference; do not duplicate its composite key. If introducing another demo release, use a new release UUID and a unique name/version pair.

After intentional expansion, update the bounded catalog counts in `genoma/tests.py` and this guide. From the repository root, validate through the guarded runner:

```bash
cd backend/sequoh && PYTHONDONTWRITEBYTECODE=1 venv/Scripts/python.exe services/tests.py genoma.tests
```

The existing v2 display-demo pipeline is separate, fixed, and checksummed; do not repurpose its fixture or custom importer for this editable catalog.
