from django.contrib import admin
from .models import SNP, UserSNP, RsidExtraInfo


@admin.register(SNP)
class SNPAdmin(admin.ModelAdmin):
    list_display = (
        'rsid', 'genotipo', 'cromosoma', 'posicion',
        'nivel_riesgo', 'magnitud_efecto', 'categoria',
        'continente', 'pais', 'af_continente', 'af_pais',
        'fuente_base_datos', 'fenotipo_preview'
    )
    list_filter = (
        'categoria', 'nivel_riesgo', 'cromosoma',
        'fuente_base_datos', 'tipo_evidencia'
    )
    search_fields = (
        'rsid', 'genotipo', 'fenotipo', 'cromosoma',
        'alelo_referencia', 'alelo_alternativo'
    )
    ordering = ('rsid', 'genotipo')

    fieldsets = (
        ('Identificación', {
            'fields': ('rsid', 'genotipo', 'cromosoma', 'posicion')
        }),
        ('Alelos', {
            'fields': ('alelo_referencia', 'alelo_alternativo')
        }),
        ('Información Clínica', {
            'fields': ('fenotipo', 'nivel_riesgo', 'magnitud_efecto', 'categoria')
        }),
        ('Datos de Ancestría - Continente', {
            'fields': ('continente', 'af_continente', 'fuente_continente', 'poblacion_continente')
        }),
        ('Datos de Ancestría - País', {
            'fields': ('pais', 'af_pais', 'fuente_pais', 'poblacion_pais')
        }),
        ('Metadata', {
            'fields': ('fuente_base_datos', 'tipo_evidencia', 'fecha_actualizacion')
        }),
    )

    def fenotipo_preview(self, obj):
        """Muestra un preview del fenotipo"""
        return obj.fenotipo[:50] + '...' if len(obj.fenotipo) > 50 else obj.fenotipo
    fenotipo_preview.short_description = 'Fenotipo (preview)'


@admin.register(UserSNP)
class UserSNPAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_rsid', 'get_genotipo', 'get_categoria')
    list_filter = ('snp__categoria',)
    search_fields = ('user__username', 'user__email', 'snp__rsid')
    raw_id_fields = ('user', 'snp')

    def get_rsid(self, obj):
        return obj.snp.rsid
    get_rsid.short_description = 'rsID'

    def get_genotipo(self, obj):
        return obj.snp.genotipo
    get_genotipo.short_description = 'Genotipo'

    def get_categoria(self, obj):
        return obj.snp.categoria or '-'
    get_categoria.short_description = 'Categoría'


@admin.register(RsidExtraInfo)
class RsidExtraInfoAdmin(admin.ModelAdmin):
    list_display = ('rs_id', 'genotype', 'phenotype_name', 'freq_chile_percent')
    search_fields = ('rs_id', 'genotype', 'phenotype_name')
    ordering = ('rs_id', 'genotype')
