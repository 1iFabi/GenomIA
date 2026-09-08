"""
Management command para asignar variantes (SNPs) a un usuario concreto,
de forma que aparezcan en sus resultados.

Replica la misma lógica de prioridad que usa la carga de archivos genéticos
(upload_views.py): por cada combinación (rsid, genotipo) se elige UNA fila,
priorizando los datos de Chile > América > población con país > resto.

Dos modos de uso:

1) Asignación explícita (--rsids / --all / --genotype / --categoria):

    python manage.py assign_snps <email> --rsids rs1393350,rs1815739
    python manage.py assign_snps <email> --rsids rs1393350 --genotype "G/A"
    python manage.py assign_snps <email> --rsids rs1393350 --categoria rasgos
    python manage.py assign_snps <email> --all

2) Asignación muestral proporcional (--sample N):
    Asigna N variantes repartidas proporcionalmente entre las categorías
    según cuántas variantes tiene cada una en la base.

    python manage.py assign_snps <email> --sample 100
    python manage.py assign_snps <email> --sample 100 --seed 42
    python manage.py assign_snps <email> --sample 100 --categoria rasgos
    python manage.py assign_snps <email> --sample 100 --replace

Opciones comunes:
    --replace    Vaciar los UserSNP del usuario antes de asignar.
    --dry-run    No guardar, solo mostrar qué se asignaría.
"""

import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Case, When, IntegerField, Value

from genetics.models import SNP, UserSNP


# Misma prioridad que upload_views.py
PRIORITY = Case(
    When(pais__iexact='Chile', then=Value(0, output_field=IntegerField())),
    When(continente__icontains='america', then=Value(1, output_field=IntegerField())),
    When(poblacion_pais__isnull=False, then=Value(2, output_field=IntegerField())),
    When(pais__isnull=False, then=Value(3, output_field=IntegerField())),
    default=Value(4, output_field=IntegerField()),
    output_field=IntegerField(),
)


def _best_snp(rsid, genotype, categoria=None):
    """Elige la fila 'mejor' (Chile > América > ...) para un combo rsid+genotipo.

    Si se pasa `categoria`, restringe la búsqueda a esa categoría (evita que un
    mismo rsid+genotipo presente en varias categorías resuelva a una fila que no
    pertenece a la categoría que se está llenando).
    """
    qs = SNP.objects.filter(rsid=rsid, genotipo=genotype)
    if categoria:
        qs = qs.filter(categoria=categoria)
    return (
        qs
        .annotate(priority=PRIORITY)
        .order_by('priority', '-af_pais', 'id')
        .first()
    )


def _allocate(sizes, total):
    """Reparte `total` asientos proporcionalmente a `sizes` (método de mayor residuo).

    Devuelve un dict {clave: cantidad} que suma exactamente `total`, sin que
    ninguna cantidad supere el tamaño de su categoría (redistribuye sobrante).
    """
    keys = list(sizes.keys())
    if not keys:
        return {}

    total_size = sum(sizes.values())
    if total_size == 0:
        return {k: 0 for k in keys}

    share = {k: sizes[k] * total / total_size for k in keys}
    alloc = {k: int(share[k]) for k in keys}
    remaining = total - sum(alloc.values())
    if remaining < 0:
        remaining = 0

    # Ordenar por residuo descendente (mayor parte fraccionaria)
    order = sorted(keys, key=lambda k: share[k] - alloc[k], reverse=True)

    # Repartir el sobrante respetando el tope de cada categoría
    idx = 0
    while remaining > 0:
        k = order[idx % len(order)]
        if alloc[k] < sizes[k]:
            alloc[k] += 1
            remaining -= 1
        idx += 1
        if idx > len(order) * 200:  # salvaguarda: no debería ocurrir
            break

    return alloc


class Command(BaseCommand):
    help = 'Asocia variantes (SNPs) a un usuario para que aparezcan en sus resultados.'

    def add_arguments(self, parser):
        parser.add_argument('email', help='Email del usuario destino.')
        parser.add_argument(
            '--rsids',
            help='rsIDs separados por comas (ej: rs1393350,rs1815739).',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Asignar todos los SNPs de la base de datos.',
        )
        parser.add_argument(
            '--sample',
            type=int,
            help='Asignar N variantes repartidas proporcionalmente entre categorías.',
        )
        parser.add_argument('--genotype', help='Filtrar por genotipo exacto (ej: "G/A").')
        parser.add_argument('--categoria', help='Filtrar por categoría (ej: rasgos).')
        parser.add_argument('--seed', type=int, help='Semilla para muestreo reproducible.')
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Vaciar los UserSNP del usuario antes de asignar.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se asignaría sin guardar nada.',
        )

    def handle(self, *args, **options):
        email = options['email']
        rsids = options['rsids']
        all_snps = options['all']
        sample = options['sample']
        genotype = options['genotype']
        categoria = options['categoria']
        seed = options['seed']
        replace = options['replace']
        dry_run = options['dry_run']

        # 1) Usuario
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'No existe ningún usuario con email "{email}".'))
            return

        rng = random.Random(seed)

        if sample:
            rows = self._collect_sample(sample, categoria, rng)
        else:
            rows = self._collect_explicit(rsids, all_snps, categoria, genotype)

        if not rows:
            return

        # 2) Resumen por categoría
        by_cat = {}
        for snp in rows:
            cat = snp.categoria or 'sin_categoria'
            by_cat.setdefault(cat, []).append(snp)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY-RUN] Se asignarían {len(rows)} variantes a {email}:'
                )
            )
            for cat, snps in sorted(by_cat.items()):
                self.stdout.write(f'  {cat}: {len(snps)}')
            sample_show = [f'{s.rsid}/{s.genotipo}' for s in rows[:8]]
            if sample_show:
                self.stdout.write('  ... ' + ', '.join(sample_show))
            return

        # 3) Opcional: reemplazar
        if replace:
            deleted, _ = UserSNP.objects.filter(user=user).delete()
            self.stdout.write(f'[{email}] UserSNP previos eliminados: {deleted}')

        # 4) Asociar (get_or_create = idempotente)
        newly = 0
        already = 0
        for snp in rows:
            _, created = UserSNP.objects.get_or_create(user=user, snp=snp)
            if created:
                newly += 1
            else:
                already += 1

        # 5) Resumen
        self.stdout.write(
            self.style.SUCCESS(
                f'\nAsignación completada para {email}:\n'
                f'  - Nuevas asociaciones: {newly}\n'
                f'  - Ya existentes: {already}\n'
                f'  - Total UserSNP del usuario: {UserSNP.objects.filter(user=user).count()}'
            )
        )

    # ------------------------------------------------------------------
    def _collect_explicit(self, rsids, all_snps, categoria, genotype):
        """Modo explícito: --rsids / --all / --categoria / --genotype."""
        qs = SNP.objects.all()

        if all_snps:
            pass
        elif rsids:
            rsid_list = [r.strip() for r in rsids.split(',') if r.strip()]
            if not rsid_list:
                self.stderr.write(self.style.ERROR('--rsids está vacío.'))
                return []
            qs = qs.filter(rsid__in=rsid_list)
        else:
            self.stderr.write(
                self.style.ERROR('Debés indicar --rsids, --all o --sample. Nada que hacer.')
            )
            return []

        if categoria:
            qs = qs.filter(categoria=categoria)
        if genotype:
            qs = qs.filter(genotipo=genotype)

        combos = qs.values('rsid', 'genotipo').distinct()
        if combos.count() == 0:
            self.stdout.write(
                self.style.WARNING('No hay SNPs que coincidan con el filtro.')
            )
            return []

        rows = []
        for combo in combos:
            best = _best_snp(combo['rsid'], combo['genotipo'], categoria)
            if best is not None:
                rows.append(best)

        self._print_collected_mode('asignación explícita', len(rows), combos.count())
        return rows

    # ------------------------------------------------------------------
    def _collect_sample(self, sample, categoria, rng):
        """Modo muestral: reparte `sample` proporcionalmente entre categorías."""
        pool = SNP.objects.all()
        if categoria:
            pool = pool.filter(categoria=categoria)

        # Agrupar combos (rsid, genotipo) por categoría
        cat_combos = {}
        for cat in pool.values_list('categoria', flat=True).distinct():
            combos = list(
                pool.filter(categoria=cat).values_list('rsid', 'genotipo').distinct()
            )
            if combos:
                cat_combos[cat] = combos

        if not cat_combos:
            self.stdout.write(self.style.WARNING('No hay SNPs disponibles.'))
            return []

        sizes = {cat: len(v) for cat, v in cat_combos.items()}
        alloc = _allocate(sizes, sample)

        self.stdout.write(
            self.style.NOTICE(
                f'Reparto proporcional de {sample} entre categorías (pool={sum(sizes.values())}):'
            )
        )
        for cat, k in sorted(alloc.items()):
            self.stdout.write(f'  {cat}: {k} (disponibles {sizes[cat]})')

        rows = []
        for cat, k in alloc.items():
            if k <= 0:
                continue
            chosen = rng.sample(cat_combos[cat], min(k, len(cat_combos[cat])))
            for rsid, g in chosen:
                best = _best_snp(rsid, g, cat)
                if best is not None:
                    rows.append(best)

        return rows

    def _print_collected_mode(self, mode, n_rows, n_combos):
        self.stdout.write(
            self.style.NOTICE(f'[{mode}] {n_rows} variantes a asignar ({n_combos} combinaciones rsid+genotipo).')
        )
