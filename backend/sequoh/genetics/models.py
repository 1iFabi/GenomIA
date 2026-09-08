from django.db import models
from django.conf import settings


class SNP(models.Model):
    """
    Modelo para almacenar información de SNPs (Single Nucleotide Polymorphisms)
    """
    pharmacogenetic_system = models.ForeignKey(
        'PharmacogeneticSystem',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='snps',
        verbose_name="Sistema Farmacogenetico"
    )
    # Campos básicos
    rsid = models.CharField(max_length=20, verbose_name="rsID")
    genotipo = models.CharField(max_length=10, verbose_name="Genotipo")
    fenotipo = models.TextField(verbose_name="Fenotipo")
    categoria = models.CharField(max_length=50, blank=True, null=True, verbose_name="Categoría")
    grupo = models.CharField(max_length=100, blank=True, null=True, verbose_name="Grupo del Rasgo")

    # Campos genómicos
    cromosoma = models.CharField(max_length=5, blank=True, null=True, verbose_name="Cromosoma")
    posicion = models.BigIntegerField(blank=True, null=True, verbose_name="Posición genómica")
    alelo_referencia = models.CharField(max_length=50, blank=True, null=True, verbose_name="Alelo de referencia")
    alelo_alternativo = models.CharField(max_length=50, blank=True, null=True, verbose_name="Alelo alternativo")

    # Campos clínicos
    nivel_riesgo = models.CharField(max_length=50, blank=True, null=True, verbose_name="Nivel de riesgo")
    magnitud_efecto = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Magnitud del efecto")

    # Metadata
    fuente_base_datos = models.CharField(max_length=100, blank=True, null=True, verbose_name="Fuente de base de datos")
    tipo_evidencia = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tipo de evidencia")
    fecha_actualizacion = models.CharField(max_length=10, blank=True, null=True, verbose_name="Fecha de actualización")

    # Datos de Ancestría - Continente
    continente = models.CharField(max_length=50, blank=True, null=True, verbose_name="Continente")
    af_continente = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True, verbose_name="Frecuencia Alélica - Continente")
    fuente_continente = models.CharField(max_length=100, blank=True, null=True, verbose_name="Fuente - Continente")
    poblacion_continente = models.CharField(max_length=50, blank=True, null=True, verbose_name="Población - Continente")

    # Datos de Ancestría - País
    pais = models.CharField(max_length=50, blank=True, null=True, verbose_name="País")
    af_pais = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True, verbose_name="Frecuencia Alélica - País")
    fuente_pais = models.CharField(max_length=100, blank=True, null=True, verbose_name="Fuente - País")
    poblacion_pais = models.CharField(max_length=50, blank=True, null=True, verbose_name="Población - País")

    class Meta:
        db_table = 'snps'
        verbose_name = 'SNP'
        verbose_name_plural = 'SNPs'
        unique_together = [('rsid', 'genotipo', 'fenotipo', 'categoria')]
        indexes = [
            models.Index(fields=['rsid']),
            models.Index(fields=['categoria']),
            models.Index(fields=['cromosoma']),
            models.Index(fields=['nivel_riesgo']),
        ]

    def __str__(self):
        return f"SNP({self.rsid}, {self.genotipo})"


class RsidExtraInfo(models.Model):
    """
    Extra info for rsid/genotype/phenotype combos used in reports.
    """
    rs_id = models.CharField(max_length=20, verbose_name="rsID")
    genotype = models.CharField(max_length=10, verbose_name="Genotype")
    phenotype_name = models.TextField(verbose_name="Phenotype name")
    freq_chile_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Chile frequency percent",
    )
    phenotype_description = models.TextField(verbose_name="Phenotype description")

    class Meta:
        db_table = 'rsid_extra_info'
        verbose_name = 'RSID extra info'
        verbose_name_plural = 'RSID extra info'
        unique_together = [('rs_id', 'genotype', 'phenotype_name')]
        indexes = [
            models.Index(fields=['rs_id'], name='rsid_extra_rsid_idx'),
            models.Index(fields=['phenotype_name'], name='rsid_extra_pheno_idx'),
        ]

    def __str__(self):
        return f"RsidExtraInfo({self.rs_id}, {self.genotype})"


class UserSNP(models.Model):
    """
    Modelo de relación entre usuarios y sus SNPs
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_snps',
        verbose_name="Usuario"
    )
    snp = models.ForeignKey(
        SNP,
        on_delete=models.CASCADE,
        related_name='user_associations',
        verbose_name="SNP"
    )

    class Meta:
        db_table = 'user_snps'
        verbose_name = 'SNP de Usuario'
        verbose_name_plural = 'SNPs de Usuarios'
        unique_together = [('user', 'snp')]
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['snp']),
        ]

    def __str__(self):
        return f"UserSNP(user={self.user_id}, snp={self.snp_id})"


class PharmacogeneticSystem(models.Model):
    """Sistema o grupo para clasificar SNPs farmacogenéticos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre del Sistema')
    description = models.TextField(blank=True, null=True, verbose_name='Descripción')

    class Meta:
        verbose_name = 'Sistema Farmacogenético'
        verbose_name_plural = 'Sistemas Farmacogenéticos'

    def __str__(self):
        return self.name
