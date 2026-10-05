# Prepare a public ClinVar variant catalog — no database load

Use `python -m genoma.public_variant_preparation` to prepare 10,000 eligible
ClinVar GRCh38 alleles, an attributed Django-compatible JSON fixture, and an
integrity manifest outside Git. This stdlib-only module never imports Django,
reads project settings, connects to a database, or automatically loads anything.
This is catalog preparation, not an operational or clinical demo.

## Quick path

Run from `backend/sequoh` with an existing **outside-repository parent directory**.
The selected cache and output directories must **not exist**, even if empty.
For example, first provision `C:/GenomiaPublicPreparation` outside this checkout:

```bash
python -B -m genoma.public_variant_preparation \
  --source clinvar-grch38 --date 20260928 --limit 10000 \
  --cache-dir C:/GenomiaPublicPreparation/clinvar-20260928-cache \
  --output-dir C:/GenomiaPublicPreparation/clinvar-20260928-first10000
```

This command is the future real-source preparation path; it downloads the full
compressed snapshot, not just the selected records. No real bulk download was
performed to implement this module. Unit-test inputs are deliberately artificial
and do **not** establish downloaded biological facts.

On success, exit status is 0 and stdout contains the manifest as JSON:

| Directory | Files |
|---|---|
| Cache | `clinvar_20260928.vcf.gz` and its `.md5` sidecar |
| Output | `catalog.json`, `preview.json`, `manifest.json` |

For 10,000 selected alleles, expect **50,001 fixture objects**: one DataRelease,
then one Variant, VariantPlacement, ReleaseVariant, ExternalIdentifier, and
VariantAnnotation per allele. Inspect `selection`, `source`, and `fixture` in
the manifest before considering any further operation. The five-record preview
is for inspecting source representations, not clinical conclusions.

## Offline preparation

Use an external source directory containing only the expected dated pair of
regular, non-symlink input files. Other files are not read. Choose fresh cache
and output directories; an existing successful cache can be the offline input:

```bash
python -B -m genoma.public_variant_preparation \
  --date 20260928 --limit 10000 \
  --local-source-dir C:/GenomiaPublicPreparation/clinvar-20260928-cache \
  --cache-dir C:/GenomiaPublicPreparation/offline-copy-cache \
  --output-dir C:/GenomiaPublicPreparation/offline-first10000
```

Offline mode verifies the full source against the **local** sidecar, but cannot
prove that sidecar came from NCBI. Its manifest and fixture metadata explicitly
mark `local_input_not_publisher_authenticated`. In particular, synthetic test
files in this mode are never certified as public biological data.

Python API: `prepare(cache_dir=..., output_dir=..., date='20260928', limit=10000,
local_source_dir=None)` returns the manifest after successful file writes.
`validate_catalog(objects)` checks the six-model identities and relationships;
it is neither a DB collision check nor a reference-sequence validator.

## Source, integrity and data-use policy

- Publisher: **NCBI ClinVar and contributing submitters**. Attribute these sources
  wherever prepared data or source assertions are displayed or redistributed.
- Snapshot: <https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar_20260928.vcf.gz>.
  The CLI permits other valid dated snapshots in this same official directory;
  it does not accept arbitrary network URLs or a mutable `latest` alias.
- Sidecar: the snapshot URL plus `.md5`. The publisher's MD5 is read each run,
  and compared against **all compressed bytes**, even when the cap is already met.
  MD5 here is a publisher integrity comparison, not a cryptographic authenticity
  guarantee. HTTPS supplies the transport provenance in network mode.
- The sidecar may contain an absolute UNIX producer path. Only its exact dated
  basename is checked; the producer path is recorded as evidence and never used
  as a local input/output path. No checksum is hard-coded or inferred from a prefix.
- Local SHA256 is calculated separately for the complete source, sidecar,
  prepared fixture, and preview. The fixture checksum is not a publisher checksum.
- Data-use policy: <https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/>.
  This is the actual publisher policy, **not** an invented CC0/SPDX designation
  or a claim of unrestricted licensing. NIH does not independently validate
  submitted assertions; do not use this output for direct diagnostic or medical
  decisions without appropriately qualified review.
- Source scope: <https://www.ncbi.nlm.nih.gov/clinvar/docs/ftp_primer/> and
  <https://www.ncbi.nlm.nih.gov/clinvar/intro/>. ClinVar is a freely accessible
  archive of submitted assertions, not a representative population cohort.

The parent observed a bounded HTTP 206 prefix with VCFv4.1,
`##fileDate=2026-09-28`, `##source=ClinVar`, `##reference=GRCh38`, and eight columns.
That observation informed header handling; it did not verify the complete file.
Preparation requires a full HTTP 200 response and verifies header build/date
against the requested snapshot rather than trusting its filename.

## Selection and serialization contract

| Topic | Behavior |
|---|---|
| Selection | First eligible alleles in source order; exactly the requested positive cap, default 10,000. **Not representative** of any population. |
| Coordinates | Raw VCF POS/REF/ALT unchanged; 1-based inclusive reference span ends at `POS + len(REF) - 1`. VCF left-shifting is not HGVS right-shifting. |
| Supported | Literal uppercase A/C/G/T alleles shorter than 10kb on `1`–`22`, `X`, `Y`, `MT`; SNV, MNV, anchored insertion/deletion or delins representations. |
| Skipped | Multiallelic ALT, symbolic/breakend/spanning-deletion ALT, unsupported contigs, filtered rows, alleles at least 10kb, non-ACGT alleles, and no-change REF/ALT. Reasons/counts cover the full scanned source. |
| Rejected | Malformed rows/headers/INFO/escapes, missing or ambiguous positive ALLELEID/VariationID, coordinate overflow, duplicate allele/source-record/coordinate identities, insufficient eligible count, checksum/gzip failures. Unsupported rows still require unambiguous identity; they are not a bypass for malformed data. |
| Allele concept | Variant identity anchors to source ClinVar ALLELEID. `clinvar.allele` accession uses version `unversioned`, meaning the source supplied no allele version; snapshot lives in `source_release`. |
| Shared rsIDs | Raw RS and VariationID remain in the attributed annotation payload. No dbSNP unique-owner mappings, fake accessions, or silently merged alleles. Other INFO fields, including gene, classification, review, conditions, citations and consequence assertions, are retained losslessly. |
| Typed assertions | A single usable gene symbol and length-compatible raw significance/review/citation strings may populate typed fields. Ambiguous or oversized values stay in payload with omission reasons, never silently truncated. Assertions are not validated clinical conclusions. |
| Surrogate IDs | UUIDv5 internal keys are deterministic, not invented biological/VRS/accession identifiers. Annotation identity is transformation/snapshot/placement-versioned. |
| Validation status | `vrs_id=null`, `normalized=false`, `is_canonical=false`; no reference-sequence checking or published/frozen clinical release claim. Release status is `prepared`. |
| Timestamp | Snapshot midnight is an explicit deterministic **serialization timestamp**, not an invented download/creation time. |
| Membership | Composite key order is `[release_id, variant_id]`; placement owner and GRCh38 assembly must agree with membership/release. |

The full gzip stream is scanned through EOF/CRC, including records after the
selected cap. Duplicate source identities anywhere in that stream cause rejection.
No alleles are invented to fill an unmet cap. No accounts, patients, samples,
genotypes, frequencies, analyses, artifacts, workflow or publication rows are emitted.

## Safety and resource limits

The downloader follows only exact dated official source/sidecar HTTPS targets;
redirect policy checks happen **before** following. Ambient proxies are disabled.
HTTP encoding/partial responses, conflicting response metadata and truncated
content are rejected. Limits: 30-second socket timeout, 30-minute acquisition
budget, 512MiB compressed, 4GiB decompressed, 1MiB per line, 16MiB headers,
8KiB sidecar, five million records, and at most 100,000 selected variants.
These defaults are **hard ceilings**, including for programmatic callers. The
API accepts a `Bounds` instance with exactly its declared fields; every value
must be a positive built-in integer (not a boolean) at or below its ceiling.
Overrides may only tighten limits for tests/controlled use. Invalid bounds raise
`PreparationError` before limit comparisons, path checks or acquisition/file I/O.

Full-source duplicate checks use exact external merge sorting of typed AlleleID,
VariationID and coordinate SHA256 keys, not all-record in-memory sets or a database.
The private working ceilings are 4MiB of encoded keys (including newline bytes),
32,768 buffered entries, 4,096 initial runs and 16 merge inputs plus one output
handle. Python object/sort overhead and bounded run metadata are additional memory.
Each identity entry is at most 257 bytes; a source record contributes at most
580 bytes. Live scratch payload is capped at `2 * bounds.max_records * 580`
bytes (5,800,000,000 bytes at the default cap), covering input runs plus one merge
output. Filesystem metadata/allocation overhead, the source cache and final JSON
are additional disk use. More merge passes increase I/O, not retained identity keys.
Only keys are sorted: selected records and serialized objects retain source order.

Scratch files are exclusively created inside the newly owned cache; no ambient
temporary directory, local input directory, SQLite, shelve or other database is
used. Successful preparation removes every scratch file, leaving only the dated
source and sidecar in the cache. Merge/read/partial-write failures close handles
before owned cleanup; cleanup attempts all owned files even if one unlink fails.
Foreign files are never adopted or recursively deleted. Denied cleanup is a
reported failure, not successful preparation, and requires manual inspection.

Plan disk space for these scratch files, a full source cache and expanded JSON.
Selected records, catalog objects and JSON text/bytes still depend on the selected
cap and payload sizes; this change does **not** promise constant total RSS or an
unmeasured production peak. Artificial fixed-selection tracemalloc tests exclude
input construction and exercise small private buffers/multiple merge passes;
they are algorithm evidence, not a production capacity estimate. This preparer
fails rather than relax safety limits if a future snapshot grows or changes format.

Existing cache/output directories are never adopted or overwritten. Caught
acquisition, validation or write failures remove only newly owned files and
directories; local inputs remain intact. The manifest is written last as the
completion marker. Hard process termination, power loss or denied cleanup may
leave an incomplete directory: treat it as failed, inspect manually, and choose
new directories for a retry. Never treat `catalog.json` alone as success.

## Review checklist and next step

- [ ] Confirm the manifest matches source header, full-source MD5 and local SHA256.
- [ ] Confirm acquisition authenticity, counts, skip reasons, fixture checksum and attribution.
- [ ] Confirm there are no unsupported models, inferred clinical conclusions or population claims.
- [ ] Keep generated caches and bulk fixtures outside Git.

**Stop at prepared files.** Do not blindly run `loaddata` against the default DB.
A future separately authorized load requires collision/ownership review for
UUIDs, DataRelease name/version, source accessions and composite keys. Stable
IDs span repeated runs, snapshot changes and different caps: generic fixture
reload can overwrite existing local edits and source-release metadata. Loading
does not publish, validate or freeze a release. This task authorizes none of it.

Disposable guarded tests exercise actual Django deserialization/`loaddata`,
composite FKs, exact serialized values, reload replacement and preservation of
existing catalog/auth/workflow rows, only in `gdb_test_*` PostgreSQL databases.
They are compatibility evidence, not evidence of a real ClinVar bulk download.
