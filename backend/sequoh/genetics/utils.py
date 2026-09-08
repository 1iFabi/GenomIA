from .models import RsidExtraInfo


def build_rsid_extra_info_map(snps):
    rs_ids = set()
    genotypes = set()
    phenotypes = set()

    for snp in snps:
        if not snp:
            continue
        if snp.rsid:
            rs_ids.add(snp.rsid)
        if snp.genotipo:
            genotypes.add(snp.genotipo)
        phenotype = (snp.fenotipo or "N/D").strip() or "N/D"
        phenotypes.add(phenotype)

    if not rs_ids or not genotypes or not phenotypes:
        return {}

    extras = RsidExtraInfo.objects.filter(
        rs_id__in=rs_ids,
        genotype__in=genotypes,
        phenotype_name__in=phenotypes,
    )
    return {(row.rs_id, row.genotype, row.phenotype_name): row for row in extras}
