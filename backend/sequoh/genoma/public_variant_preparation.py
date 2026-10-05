"""Prepare attributed ClinVar catalog files without importing or connecting to Django.

Only preparation is supported. Generated fixtures are NOT authorization to load a DB.
"""

import argparse
from collections import Counter
from contextlib import ExitStack, closing
from dataclasses import dataclass
from datetime import datetime
import gzip
import heapq
import hashlib
import json
from pathlib import Path, PurePosixPath
import string
import sys
import time
from urllib.parse import unquote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid
import zlib


DEFAULT_DATE = '20260928'
BASE_URL = 'https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/'
POLICY_URL = 'https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/'
PRIMER_URL = 'https://www.ncbi.nlm.nih.gov/clinvar/docs/ftp_primer/'
TRANSFORM_VERSION = 'public-variant-preparation-v1'
IDENTITY_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, 'genomia/' + TRANSFORM_VERSION)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COLUMNS = '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO'
CONTIGS = {str(number) for number in range(1, 23)} | {'X', 'Y', 'MT'}
DISCLAIMER = (
    'Non-clinical catalog preparation only. ClinVar contains submitted assertions; '
    'NIH does not independently validate them. No diagnostic conclusion, reference '
    'sequence validation, genotype, frequency, haplotype or population claim is made.'
)


class PreparationError(ValueError):
    """Unsafe, unsupported or incomplete preparation; no successful outputs."""


@dataclass(frozen=True)
class Bounds:
    max_compressed: int = 512 * 1024 * 1024
    max_uncompressed: int = 4 * 1024 * 1024 * 1024
    max_line: int = 1024 * 1024
    max_sidecar: int = 8192
    max_header: int = 16 * 1024 * 1024
    max_records: int = 5_000_000
    max_selected: int = 100_000
    timeout: int = 30
    total_seconds: int = 1800


def validate_bounds(bounds):
    """API overrides may only tighten the default hard resource ceilings."""
    if type(bounds) is not Bounds:
        raise PreparationError('Resource bounds must be a Bounds instance')
    ceilings = vars(Bounds())
    values = vars(bounds)
    if values.keys() != ceilings.keys():
        raise PreparationError('Bounds must contain exactly the declared resource fields')
    for name, ceiling in ceilings.items():
        value = values[name]
        if type(value) is not int or not 1 <= value <= ceiling:
            raise PreparationError(f'Bounds.{name} must be a positive non-bool integer <= {ceiling}')


def snapshot_date(value):
    if not isinstance(value, str) or len(value) != 8 or not value.isascii() or not value.isdigit():
        raise PreparationError('Snapshot date must be YYYYMMDD')
    try:
        return datetime.strptime(value, '%Y%m%d').date()
    except ValueError as exc:
        raise PreparationError('Invalid snapshot date') from exc


def source_url(date):
    snapshot_date(date)
    return BASE_URL + f'clinvar_{date}.vcf.gz'


class OfficialRedirects(HTTPRedirectHandler):
    """Check exact official targets before urllib follows a redirect."""

    def __init__(self, allowed):
        super().__init__()
        self.allowed = frozenset(allowed)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if newurl not in self.allowed or req.full_url not in self.allowed:
            raise PreparationError('Redirect outside the dated official source/sidecar')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def official_opener(date):
    url = source_url(date)
    # Do not consult proxy environment variables or ambient credential handlers.
    return build_opener(ProxyHandler({}), OfficialRedirects({url, url + '.md5'}))


def outside_repository(path):
    path = Path(path)
    if path.is_symlink():
        raise PreparationError('Symlink paths are not accepted')
    resolved = path.resolve()
    if resolved == REPOSITORY_ROOT or REPOSITORY_ROOT in resolved.parents:
        raise PreparationError('Source, cache and output must be outside the repository')
    return resolved


class OwnedDirectory:
    """Exclusive new directory; failure cleanup touches only files created here."""

    def __init__(self, path):
        self.path = path
        self.files = []
        self.complete = False

    def __enter__(self):
        self.path.mkdir()  # Parent must exist; never adopt an existing directory.
        return self

    def create(self, name):
        path = self.path / name
        stream = path.open('xb')
        self.files.append(path)
        return stream

    def discard(self, path):
        # Retain ownership if unlink fails so failure cleanup can still attempt it.
        if path not in self.files:
            raise PreparationError('Cannot remove an unowned preparation file')
        path.unlink()
        self.files.remove(path)

    def __exit__(self, exc_type, exc, traceback):
        if not self.complete:
            errors = []
            for path in reversed(self.files[:]):
                try:
                    self.discard(path)
                except OSError as error:
                    errors.append(error)
            try:
                self.path.rmdir()  # Never recursive: foreign files must survive.
            except OSError as error:
                errors.append(error)
            if errors:
                raise PreparationError(f'Owned cleanup failed; inspect {self.path}: {errors[0]}') from exc


def copy_bounded(stream, destination, maximum, deadline, expected=None):
    total = 0
    while True:
        if time.monotonic() > deadline:
            raise PreparationError('Source acquisition deadline exceeded')
        block = stream.read(min(64 * 1024, maximum - total + 1))
        if not block:
            break
        total += len(block)
        if total > maximum:
            raise PreparationError('Source size bound exceeded')
        destination.write(block)
    if not total or expected is not None and total != expected:
        raise PreparationError('Empty or truncated source response')
    return total


def download(opener, url, directory, name, maximum, bounds, deadline):
    request = Request(url, headers={'Accept-Encoding': 'identity', 'User-Agent': TRANSFORM_VERSION})
    with opener.open(request, timeout=bounds.timeout) as response:
        if response.geturl() != url or response.status != 200:
            raise PreparationError('Unexpected source URL or HTTP status (full 200 required)')
        headers = response.headers
        if headers.get('Content-Encoding', 'identity').lower() != 'identity' or headers.get('Content-Range'):
            raise PreparationError('Encoded or partial HTTP response is not a complete source')
        length = headers.get('Content-Length')
        expected = None
        if length is not None:
            if not length.isascii() or not length.isdigit() or len(length) > 20:
                raise PreparationError('Invalid Content-Length metadata')
            expected = int(length)
            if expected < 1 or expected > maximum:
                raise PreparationError('HTTP source size bound exceeded')
        with directory.create(name) as destination:
            return copy_bounded(response, destination, maximum, deadline, expected)


def copy_local(source, directory, name, maximum, deadline):
    path = source / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise PreparationError('Local source must be a bounded regular file, not a symlink')
    with path.open('rb') as stream, directory.create(name) as destination:
        return copy_bounded(stream, destination, maximum, deadline)


def parse_sidecar(data, filename):
    try:
        parts = data.decode('ascii').strip().split()
    except UnicodeError as exc:
        raise PreparationError('Non-ASCII checksum sidecar') from exc
    if len(parts) != 2 or len(parts[0]) != 32 or any(c not in string.hexdigits for c in parts[0]):
        raise PreparationError('Expected exactly one MD5 filename entry')
    producer_name = parts[1].removeprefix('*')
    producer_path = PurePosixPath(producer_name)
    # The publisher uses an absolute UNIX producer path. It is evidence, NEVER an I/O path.
    if producer_path.name != filename or '..' in producer_path.parts or '\\' in producer_name:
        raise PreparationError('Checksum filename does not match the dated source')
    return parts[0].lower(), producer_name


def source_integrity(path, expected_md5):
    md5, sha256 = hashlib.md5(), hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(64 * 1024), b''):
            md5.update(block)
            sha256.update(block)
    if md5.hexdigest() != expected_md5:
        raise PreparationError('Full compressed source MD5 mismatch')
    return sha256.hexdigest()


def positive_identifier(value, label, maximum=255):
    if (not isinstance(value, str) or not value.isascii() or not value.isdigit()
            or len(value) > maximum or value.startswith('0')):
        raise PreparationError(f'Invalid or ambiguous {label}')
    return value


def decode_info(raw):
    result = {}
    for part in raw.split(';'):
        key, separator, value = part.partition('=')
        if not key or any(c not in string.ascii_letters + string.digits + '_.-' for c in key):
            raise PreparationError('Malformed INFO key')
        if key in result:
            raise PreparationError('Duplicate INFO key')
        if not separator:
            result[key] = True
            continue
        # Split delimiters FIRST; decoding %3B/%3D cannot create extra fields.
        index = 0
        while index < len(value):
            if value[index] == '%':
                if len(value[index:index + 3]) != 3 or any(
                    c not in string.hexdigits for c in value[index + 1:index + 3]
                ):
                    raise PreparationError('Malformed percent escape in INFO')
                index += 3
            else:
                index += 1
        decoded = unquote(value, encoding='utf-8', errors='strict')
        if '\x00' in decoded:
            raise PreparationError('NUL cannot be serialized into PostgreSQL JSON')
        result[key] = decoded
    return result


def bounded_lines(path, bounds):
    total = 0
    with gzip.open(path, 'rb') as stream:
        while True:
            raw = stream.readline(bounds.max_line + 1)
            if not raw:
                break  # Reading EOF verifies the gzip trailer/CRC, even beyond the cap.
            total += len(raw)
            if len(raw) > bounds.max_line or total > bounds.max_uncompressed:
                raise PreparationError('VCF decompression or line size bound exceeded')
            if not raw.endswith(b'\n'):
                raise PreparationError('Incomplete VCF line')
            yield raw.decode('utf-8').rstrip('\r\n'), len(raw)


def parse_record(line, line_number):
    columns = line.split('\t')
    if len(columns) != 8 or any('\x00' in column for column in columns):
        raise PreparationError(f'Malformed eight-column VCF record at line {line_number}')
    chrom, pos, record_id, ref, alt, quality, filters, raw_info = columns
    positive_identifier(pos, 'POS', 19)
    start = int(pos)
    if not ref or not alt or start + len(ref) - 1 > 2 ** 63 - 1:
        raise PreparationError('Invalid allele or reference span')
    positive_identifier(record_id, 'VariationID')
    info = decode_info(raw_info)
    allele = positive_identifier(info.get('ALLELEID'), 'ALLELEID')
    record = {
        'contig': chrom, 'pos': start, 'record_id': record_id, 'ref': ref, 'alt': alt,
        'quality': quality, 'filter': filters, 'allele_id': allele, 'info': info,
        'raw_info': raw_info, 'raw_record': line, 'line_number': line_number,
    }
    reason = None
    if ',' in alt:
        reason = 'multiallelic'
    elif any(c in alt for c in '<>[]*'):
        reason = 'symbolic_or_breakend'
    elif chrom not in CONTIGS:
        reason = 'unsupported_contig'
    elif filters not in ('.', 'PASS'):
        reason = 'filtered'
    elif len(ref) >= 10_000 or len(alt) >= 10_000:
        reason = 'allele_length_at_least_10kb'
    elif any(c not in 'ACGT' for c in ref + alt):
        reason = 'non_acgt_allele'
    elif ref == alt:
        reason = 'no_change'
    return record, reason


# Private, fixed working ceilings; tests may tighten them to exercise merge passes.
_IDENTITY_BUFFER_BYTES = 4 * 1024 * 1024
_IDENTITY_BUFFER_ENTRIES = 32768
_IDENTITY_MERGE_FAN_IN = 16
_IDENTITY_MAX_RUNS = 4096
_IDENTITY_ENTRY_BYTES = 257  # Type + 255-digit accession + newline.
_IDENTITY_BYTES_PER_RECORD = 580  # Two 257-byte IDs + a 66-byte coordinate SHA256 key.
_IDENTITY_LABELS = {b'A': 'AlleleID/source accession', b'V': 'VariationID/source record',
                    b'C': 'assembly/coordinate/REF/ALT'}


@dataclass(frozen=True)
class _IdentityRun:
    name: str
    size: int
    entries: int


class _DiskIdentities:
    """Exact external sorting, not a database or probabilistic membership filter.

    Only typed keys are sorted; selected biological records retain source order.
    Run metadata is capped separately from key-buffer bytes and entry count.
    Every scratch file is exclusively created and tracked by the owned cache.
    """

    def __init__(self, cache, bounds):
        self.cache = cache
        self.buffer, self.runs = [], []
        self.buffer_bytes = self.scratch_bytes = self.serial = 0
        self.storage_limit = 2 * bounds.max_records * _IDENTITY_BYTES_PER_RECORD
        self.peak_buffer_bytes = self.peak_buffer_entries = self.peak_scratch_bytes = 0
        self.merge_passes = 0

    @staticmethod
    def _check_key(key):
        tag, value = key[:1], key[1:]
        if tag == b'C':
            valid = len(value) == 64 and not value.strip(b'0123456789abcdef')
        else:
            valid = tag in (b'A', b'V') and 1 <= len(value) <= 255 and value.isdigit() and value[:1] != b'0'
        if not valid:
            raise PreparationError('Malformed identity scratch entry')

    @staticmethod
    def _check_order(previous, key):
        if previous == key:
            raise PreparationError(f'duplicate {_IDENTITY_LABELS[key[:1]]}; no silent merging')
        if previous is not None and key < previous:
            raise PreparationError('Unsorted identity scratch run')

    def add(self, key):
        self._check_key(key)
        size = len(key) + 1
        if size > _IDENTITY_BUFFER_BYTES:
            raise PreparationError('Identity exceeds working buffer byte ceiling')
        if self.buffer and (len(self.buffer) >= _IDENTITY_BUFFER_ENTRIES
                            or self.buffer_bytes + size > _IDENTITY_BUFFER_BYTES):
            self._flush()
        self.buffer.append(key)
        self.buffer_bytes += size
        self.peak_buffer_bytes = max(self.peak_buffer_bytes, self.buffer_bytes)
        self.peak_buffer_entries = max(self.peak_buffer_entries, len(self.buffer))

    def _write_run(self, keys, kind):
        name = f'.identity-{kind}-{self.serial:06d}.run'
        self.serial += 1
        previous = None
        size = entries = 0
        with self.cache.create(name) as stream:
            for key in keys:
                self._check_order(previous, key)
                data = key + b'\n'
                if self.scratch_bytes + len(data) > self.storage_limit:
                    raise PreparationError('Identity scratch storage ceiling exceeded')
                if stream.write(data) != len(data):
                    raise PreparationError('Short identity scratch write')
                size += len(data)
                entries += 1
                self.scratch_bytes += len(data)
                self.peak_scratch_bytes = max(self.peak_scratch_bytes, self.scratch_bytes)
                previous = key
        return _IdentityRun(name, size, entries)

    def _flush(self):
        if not self.buffer:
            return
        if len(self.runs) >= _IDENTITY_MAX_RUNS:
            raise PreparationError('Identity scratch run count ceiling exceeded')
        self.buffer.sort()
        self.runs.append(self._write_run(self.buffer, 'chunk'))
        self.buffer.clear()
        self.buffer_bytes = 0

    def _read_run(self, stream, run):
        size = 0
        previous = None
        for _ in range(run.entries):
            data = stream.readline(_IDENTITY_ENTRY_BYTES + 1)
            if not data.endswith(b'\n') or len(data) > _IDENTITY_ENTRY_BYTES:
                raise PreparationError('Incomplete or oversized identity scratch entry')
            key = data[:-1]
            self._check_key(key)
            self._check_order(previous, key)
            size += len(data)
            if size > run.size:
                raise PreparationError('Identity scratch run size mismatch')
            yield key
            previous = key
        if stream.read(1) or size != run.size:
            raise PreparationError('Truncated or extended identity scratch run')

    def _remove(self, run):
        self.cache.discard(self.cache.path / run.name)
        self.scratch_bytes -= run.size

    def _merge(self, group):
        # ExitStack closes every handle, including on read/write/duplicate errors.
        with ExitStack() as stack:
            inputs = [self._read_run(stack.enter_context((self.cache.path / run.name).open('rb')), run)
                      for run in group]
            merged = self._write_run(heapq.merge(*inputs), 'merge')
        if merged.entries != sum(run.entries for run in group):
            raise PreparationError('Identity merge entry count mismatch')
        for run in group:
            self._remove(run)  # Inputs close BEFORE unlink (required on Windows).
        return merged

    def finish(self):
        self._flush()
        while len(self.runs) > 1:
            following = []
            self.merge_passes += 1
            for offset in range(0, len(self.runs), _IDENTITY_MERGE_FAN_IN):
                group = self.runs[offset:offset + _IDENTITY_MERGE_FAN_IN]
                following.append(self._merge(group) if len(group) > 1 else group[0])
            self.runs = following
        for run in self.runs:
            with (self.cache.path / run.name).open('rb') as stream:
                for _ in self._read_run(stream, run):
                    pass  # Also verify a single chunk without any merge pass.
            self._remove(run)
        self.runs.clear()


def parse_vcf(path, date, limit, bounds, *, owned_cache):
    identities = _DiskIdentities(owned_cache, bounds)
    with closing(bounded_lines(path, bounds)) as lines:
        result = _scan_vcf(lines, date, limit, bounds, identities)
    identities.finish()  # Full EOF/CRC and global duplicate checks before outputs.
    return result


def _scan_vcf(lines, date, limit, bounds, identities):
    headers, selected, skipped = {}, [], Counter()
    column_header = False
    allele_definition = False
    header_size = records = eligible = 0
    for line_number, (line, size) in enumerate(lines, 1):
        if line.startswith('##') and not column_header:
            header_size += size
            if header_size > bounds.max_header:
                raise PreparationError('VCF header size bound exceeded')
            key, separator, value = line[2:].partition('=')
            if not separator:
                raise PreparationError('Malformed VCF metadata header')
            if key in ('fileformat', 'fileDate', 'reference', 'source'):
                if key in headers:
                    raise PreparationError('Duplicate VCF metadata header')
                headers[key] = value
            if key == 'contig':
                assemblies = [part.partition('=')[2].strip('"') for part in value.strip('<>').split(',')
                              if part.startswith('assembly=')]
                if assemblies and assemblies != ['GRCh38']:
                    raise PreparationError('Conflicting contig assembly metadata')
            if key == 'INFO' and value.startswith('<ID=ALLELEID,'):
                if allele_definition or not value.startswith('<ID=ALLELEID,Number=1,Type=Integer,'):
                    raise PreparationError('Ambiguous ALLELEID header definition')
                allele_definition = True
            continue
        if line.startswith('#') and not column_header:
            if (line != COLUMNS or not allele_definition
                    or headers.get('fileformat') not in ('VCFv4.1', 'VCFv4.2', 'VCFv4.3')
                    or headers.get('fileDate') != snapshot_date(date).isoformat()
                    or headers.get('reference') != 'GRCh38' or headers.get('source') != 'ClinVar'):
                raise PreparationError('VCF header does not confirm ClinVar assembly/date/format/identity')
            column_header = True
            continue
        if not column_header or not line or line.startswith('#'):
            raise PreparationError('Missing, repeated or misplaced VCF header/record')
        records += 1
        if records > bounds.max_records:
            raise PreparationError('VCF record count bound exceeded')
        record, reason = parse_record(line, line_number)
        coordinate = hashlib.sha256(json_bytes([
            record['contig'], record['pos'], record['ref'], record['alt'],
        ])).hexdigest().encode('ascii')
        identities.add(b'A' + record['allele_id'].encode('ascii'))
        identities.add(b'V' + record['record_id'].encode('ascii'))
        identities.add(b'C' + coordinate)
        if reason:
            skipped[reason] += 1
            continue
        eligible += 1
        if len(selected) < limit:
            selected.append(record)
    if not column_header or len(selected) != limit:
        raise PreparationError(f'Cannot meet requested eligible cap {limit}; found {len(selected)}')
    return selected, headers, {
        'method': 'first eligible records in source order; not representative of any population',
        'requested': limit, 'selected': len(selected), 'eligible': eligible,
        'eligible_not_selected': eligible - limit, 'records_scanned': records,
        'skipped': dict(sorted(skipped.items())),
    }


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode('utf-8')


def internal_id(kind, *parts):
    return str(uuid.uuid5(IDENTITY_NAMESPACE, json.dumps([kind, *parts], separators=(',', ':'))))


def allele_type(ref, alt):
    if len(ref) == len(alt):
        return 'SNV' if len(ref) == 1 else 'MNV'
    if alt.startswith(ref):
        return 'insertion'
    if ref.startswith(alt):
        return 'deletion'
    return 'delins'


def catalog_objects(records, date, provenance):
    timestamp = snapshot_date(date).isoformat() + 'T00:00:00Z'
    version = f'{date}-first-{len(records)}-p1'
    release_id = internal_id('release', version)
    objects = []

    def add(model, pk, **fields):
        objects.append({'model': 'genoma.' + model, 'pk': pk,
                        'fields': {**fields, 'created_at': timestamp}})

    add('datarelease', release_id, name='ClinVar GRCh38 preparation', version=version,
        status='prepared', reference_assembly='GRCh38', description=DISCLAIMER,
        manifest_checksum=None, frozen_at=None)
    for record in records:
        allele, info = record['allele_id'], record['info']
        variant_id = internal_id('clinvar-allele', allele)
        placement_id = internal_id('placement', allele, 'GRCh38', record['contig'],
                                   record['pos'], record['ref'], record['alt'])
        metadata = {
            'source_name': 'ClinVar', 'source_date': snapshot_date(date).isoformat(),
            'source_url': source_url(date), 'allele_id': allele,
            'source_authentication': provenance, 'reference_sequence_validated': False,
            'internal_identity_scheme': TRANSFORM_VERSION,
        }
        canonical_name = 'ClinVar AlleleID ' + allele
        add('variant', variant_id, variant_type=allele_type(record['ref'], record['alt']),
            canonical_name=canonical_name if len(canonical_name) <= 255 else None,
            vrs_id=None, status='active', metadata=metadata)
        add('variantplacement', placement_id, variant=variant_id, reference_assembly='GRCh38',
            contig=record['contig'], start_pos=record['pos'], end_pos=record['pos'] + len(record['ref']) - 1,
            coordinate_system='1-based-inclusive', reference_allele=record['ref'], alternate_allele=record['alt'],
            strand=None, sv_length=None, breakend=None, is_canonical=False, normalized=False, metadata=metadata)
        add('releasevariant', [release_id, variant_id], release=release_id, variant=variant_id,
            placement=placement_id, included_by_analysis=None, inclusion_status='included')
        add('externalidentifier', internal_id('clinvar-allele-accession', allele), variant=variant_id,
            replaced_by_identifier=None, namespace='clinvar.allele', accession=allele, version='unversioned',
            status='active', source_release=date, is_primary=True)
        omitted = {}

        def typed(field, value, maximum):
            if value is None:
                return None
            if not isinstance(value, str) or not value or len(value) > maximum:
                omitted[field] = 'unusable or exceeds model length; retained losslessly in payload'
                return None
            return value

        gene_info = info.get('GENEINFO')
        gene_symbol = None
        if isinstance(gene_info, str) and gene_info.count(':') == 1 and not any(c in gene_info for c in '|,;'):
            symbol, separator, gene_id = gene_info.rpartition(':')
            if separator and gene_id.isascii() and gene_id.isdigit():
                gene_symbol = typed('gene_symbol', symbol, 64)
        if gene_info is not None and gene_symbol is None:
            omitted['gene_symbol'] = 'ambiguous or unusable GENEINFO; retained in payload'
        fields = {
            'gene_symbol': gene_symbol,
            'clinical_significance': typed('clinical_significance', info.get('CLNSIG'), 128),
            'evidence_level': typed('evidence_level', info.get('CLNREVSTAT'), 64),
            'citation_id': typed('citation_id', info.get('CLNCIT'), 128),
        }
        add('variantannotation', internal_id('annotation', allele, date, placement_id),
            variant=variant_id, placement=placement_id, analysis=None, source_name='ClinVar', source_version=date,
            annotation_type='submitted_clinvar_assertions', transcript_id=None, consequence=None, score=None,
            payload={
                **metadata, 'assertions_independently_validated': False, 'disclaimer': DISCLAIMER,
                'info': info, 'raw_info': record['raw_info'], 'raw_record': record['raw_record'],
                'variation_id': record['record_id'], 'source_line': record['line_number'],
                'typed_fields_omitted': omitted,
            }, **fields)
    return objects


def validate_catalog(objects):
    """Validate prepared identities/ownership; not an importer or a clinical validator."""
    labels = ('datarelease', 'variant', 'variantplacement', 'releasevariant',
              'externalidentifier', 'variantannotation')
    groups = {label: {} for label in labels}
    for obj in objects:
        label = obj['model'].removeprefix('genoma.')
        if obj['model'] != 'genoma.' + label or label not in groups:
            raise PreparationError('Unsupported serialized model')
        key = obj['pk']
        if label == 'releasevariant':
            if not isinstance(key, list) or len(key) != 2:
                raise PreparationError('Membership requires release,variant composite key')
            key = tuple(key)
            keys = key
        else:
            keys = [key]
        try:
            if any(str(uuid.UUID(value)) != value for value in keys):
                raise ValueError('noncanonical UUID')
        except (ValueError, TypeError, AttributeError) as exc:
            raise PreparationError('Invalid internal UUID') from exc
        if key in groups[label]:
            raise PreparationError('duplicate serialized identity')
        groups[label][key] = obj['fields']
    releases, variants, placements, memberships, externals, annotations = (groups[label] for label in labels)
    if len(releases) != 1 or not variants or any(
        len(group) != len(variants) for group in (placements, memberships, externals, annotations)
    ):
        raise PreparationError('Inconsistent six-model catalog counts')
    release_id, release = next(iter(releases.items()))
    if release['reference_assembly'] != 'GRCh38' or release['frozen_at'] is not None:
        raise PreparationError('Invalid prepared release assembly/freeze state')
    for fields in variants.values():
        if fields['vrs_id'] is not None:
            raise PreparationError('VRS identifiers are not computed by this preparation')
    for fields in placements.values():
        if (fields['variant'] not in variants or fields['reference_assembly'] != release['reference_assembly']
                or fields['normalized'] is not False or fields['start_pos'] < 1
                or fields['end_pos'] != fields['start_pos'] + len(fields['reference_allele']) - 1):
            raise PreparationError('Invalid placement ownership/assembly/reference span')
    if {fields['variant'] for fields in placements.values()} != set(variants):
        raise PreparationError('Placement ownership is not one-to-one')
    for key, fields in memberships.items():
        placement = placements.get(fields['placement'])
        if (key != (release_id, fields['variant']) or fields['release'] != release_id
                or fields['variant'] not in variants or placement is None
                or placement['variant'] != fields['variant'] or fields['included_by_analysis'] is not None):
            raise PreparationError('Membership key order or placement/release ownership mismatch')
    source_keys = set()
    for fields in externals.values():
        source_key = (fields['namespace'], fields['accession'], fields['version'])
        if source_key in source_keys or fields['variant'] not in variants:
            raise PreparationError('duplicate or invalid source external key')
        source_keys.add(source_key)
    for fields in annotations.values():
        placement = placements.get(fields['placement'])
        if (fields['variant'] not in variants or placement is None
                or placement['variant'] != fields['variant'] or fields['analysis'] is not None):
            raise PreparationError('Annotation ownership mismatch')


def prepare(*, cache_dir, output_dir, date=DEFAULT_DATE, limit=10_000,
            local_source_dir=None, bounds=Bounds(), opener=None):
    """Acquire, verify and prepare only; return the manifest after successful writes.

    Local mode reads only the exact dated gzip/sidecar pair in an external directory.
    Its checksum is verified, but local sidecar publisher authenticity is NOT asserted.
    The optional opener is a test seam; normal CLI uses the restricted official opener.
    """
    validate_bounds(bounds)
    snapshot_date(date)
    if type(limit) is not int or not 1 <= limit <= bounds.max_selected:
        raise PreparationError(f'Limit must be a positive integer at most {bounds.max_selected}')
    cache, output = outside_repository(cache_dir), outside_repository(output_dir)
    if cache == output or cache in output.parents or output in cache.parents:
        raise PreparationError('Cache and output must be separate non-nested directories')
    for path in (cache, output):
        if path.exists():
            raise PreparationError(f'Directory exists; no overwrite: {path}')
        if not path.parent.is_dir():
            raise PreparationError('Cache/output parent directory must already exist')
    local = outside_repository(local_source_dir) if local_source_dir is not None else None
    filename = f'clinvar_{date}.vcf.gz'
    url = source_url(date)
    provenance = 'official_https_sidecar' if local is None else 'local_input_not_publisher_authenticated'
    deadline = time.monotonic() + bounds.total_seconds
    try:
        with ExitStack() as stack:
            owned_cache = stack.enter_context(OwnedDirectory(cache))
            def acquire(name, maximum):
                if local is not None:
                    copy_local(local, owned_cache, name, maximum, deadline)
                else:
                    download(opener, url + ('.md5' if name.endswith('.md5') else ''),
                             owned_cache, name, maximum, bounds, deadline)

            if local is None and opener is None:
                opener = official_opener(date)
            acquire(filename + '.md5', bounds.max_sidecar)
            sidecar = (cache / (filename + '.md5')).read_bytes()
            publisher_md5, producer_name = parse_sidecar(sidecar, filename)
            acquire(filename, bounds.max_compressed)
            source_sha256 = source_integrity(cache / filename, publisher_md5)
            records, header, selection = parse_vcf(cache / filename, date, limit, bounds,
                                                   owned_cache=owned_cache)
            objects = catalog_objects(records, date, provenance)
            validate_catalog(objects)
            fixture = json_bytes(objects)
            preview = json_bytes({
                'disclaimer': DISCLAIMER, 'source_authentication': provenance,
                'records': [{key: row[key] for key in ('allele_id', 'record_id', 'contig', 'pos', 'ref', 'alt')}
                            for row in records[:5]],
            })
            manifest = {
                'format_version': 1, 'transform_version': TRANSFORM_VERSION,
                'source': {
                    'name': 'ClinVar', 'url': url, 'date': snapshot_date(date).isoformat(),
                    'reference_assembly': 'GRCh38', 'header': header, 'acquisition': provenance,
                    'compressed_bytes': (cache / filename).stat().st_size, 'sha256': source_sha256,
                    'md5': {'value': publisher_md5, 'matched_full_compressed_source': True,
                            'publisher_authenticated': local is None, 'sidecar_url': url + '.md5',
                            'sidecar_sha256': hashlib.sha256(sidecar).hexdigest(),
                            'producer_filename': producer_name},
                },
                'selection': selection,
                'serialization_timestamp': {'value': snapshot_date(date).isoformat() + 'T00:00:00Z',
                                            'meaning': 'deterministic snapshot midnight, NOT download/creation time'},
                'identity': {'scheme': TRANSFORM_VERSION, 'variant_anchor': 'source ClinVar ALLELEID',
                             'external_version': 'unversioned means no source allele version was supplied',
                             'annotation_identity': 'versioned by transformation, snapshot and placement',
                             'uuid_meaning': 'internal UUIDv5 surrogates, NOT biological accessions or VRS IDs'},
                'data_policy': {'url': POLICY_URL, 'attribution': 'NCBI ClinVar and contributing submitters',
                                'note': 'Publisher use policy; no CC0/SPDX or unrestricted licensing assertion'},
                'representation': {'primer_url': PRIMER_URL, 'coordinates': '1-based-inclusive reference span',
                                   'source_ref_alt_pos_unchanged': True, 'normalized': False,
                                   'reference_sequence_validated': False},
                'fixture': {'filename': 'catalog.json', 'sha256': hashlib.sha256(fixture).hexdigest(),
                            'bytes': len(fixture), 'objects': len(objects),
                            'model_counts': dict(sorted(Counter(obj['model'] for obj in objects).items()))},
                'preview': {'filename': 'preview.json', 'sha256': hashlib.sha256(preview).hexdigest()},
                'bounds': vars(bounds), 'disclaimer': DISCLAIMER,
            }
            owned_output = stack.enter_context(OwnedDirectory(output))
            # Completion marker last. Failures clean both newly owned directories.
            for name, data in (('catalog.json', fixture), ('preview.json', preview),
                               ('manifest.json', json_bytes(manifest))):
                with owned_output.create(name) as stream:
                    stream.write(data)
            owned_cache.complete = owned_output.complete = True
            return manifest
    except PreparationError:
        raise
    except (OSError, EOFError, UnicodeError, zlib.error) as exc:
        raise PreparationError(f'Preparation failed ({type(exc).__name__}): {exc}') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=['clinvar-grch38'], default='clinvar-grch38')
    parser.add_argument('--date', default=DEFAULT_DATE, help='Dated snapshot YYYYMMDD (header uses ISO date)')
    parser.add_argument('--limit', type=int, default=10_000, help='Eligible variants; 1..100000, default 10000')
    parser.add_argument('--cache-dir', required=True, type=Path, help='New external source-cache directory')
    parser.add_argument('--output-dir', required=True, type=Path, help='New external prepared-output directory')
    parser.add_argument('--local-source-dir', type=Path, help='Offline exact dated gzip/sidecar pair; not authenticated')
    args = parser.parse_args(argv)
    try:
        manifest = prepare(cache_dir=args.cache_dir, output_dir=args.output_dir, date=args.date,
                           limit=args.limit, local_source_dir=args.local_source_dir)
    except PreparationError as exc:
        print(f'Preparation rejected: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
