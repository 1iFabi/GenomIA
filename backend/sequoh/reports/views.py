import json
import os
import subprocess
import tempfile
import unicodedata
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link

from profiles.models import Profile
from genetics.models import UserSNP
from profiles.utils import ensure_sample_code
from genetics.utils import build_rsid_extra_info_map

CATEGORY_ORDER = [
    "enfermedades",
    "farmacogenetica",
    "biometricas",
    "biomarcadores",
    "rasgos",
]

CATEGORY_LABELS = {
    "enfermedades": "Enfermedades",
    "farmacogenetica": "Farmacogenetica",
    "biometricas": "Biometricas",
    "biomarcadores": "Biomarcadores",
    "rasgos": "Rasgos",
}

RISK_LABELS = {
    "high": "Alto",
    "mid": "Medio",
    "low": "Bajo",
}

PAGE_WIDTH_MM = 210
PAGE_HEIGHT_MM = 297
TOC_TOP_MM = 60
TOC_ROW_HEIGHT_MM = 10
TOC_ROW_GAP_MM = 2
TOC_LEFT_MM = 18
TOC_RIGHT_MM = 18
MM_TO_PT = 72 / 25.4


def _toc_link_rect(row_index):
    top_mm = TOC_TOP_MM + row_index * (TOC_ROW_HEIGHT_MM + TOC_ROW_GAP_MM)
    bottom_mm = top_mm + TOC_ROW_HEIGHT_MM
    x1 = TOC_LEFT_MM * MM_TO_PT
    x2 = (PAGE_WIDTH_MM - TOC_RIGHT_MM) * MM_TO_PT
    y_top = (PAGE_HEIGHT_MM - top_mm) * MM_TO_PT
    y_bottom = (PAGE_HEIGHT_MM - bottom_mm) * MM_TO_PT
    return (x1, y_bottom, x2, y_top)


def _target_key_for_file(filename):
    if filename.endswith("_intro.pdf"):
        return "intro"
    if filename.endswith("_reporte.pdf"):
        return "report"
    if filename.endswith("_ancestria.pdf"):
        return "ancestry"
    if filename.endswith("_cierre.pdf"):
        return "closing"
    if "_section_" in filename:
        stem = Path(filename).stem
        if "_section_" in stem:
            category_key = stem.split("_section_")[-1]
            return f"section-{category_key}"
    return None


def _normalize_text(value):
    if not value:
        return ""
    text = str(value).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _normalize_category(value):
    norm = _normalize_text(value)
    if not norm:
        return None
    if "enfermedad" in norm:
        return "enfermedades"
    if "farmaco" in norm:
        return "farmacogenetica"
    if "biomarc" in norm:
        return "biomarcadores"
    if "biometr" in norm:
        return "biometricas"
    if "rasgo" in norm:
        return "rasgos"
    return None


def _normalize_risk(value):
    norm = _normalize_text(value)
    if not norm:
        return "low"
    if "alto" in norm or norm == "high":
        return "high"
    if "inter" in norm or "medio" in norm or norm in {"medium", "mid"}:
        return "mid"
    if "bajo" in norm or norm == "low":
        return "low"
    return "low"


def _normalize_indigenous_name(raw_name):
    if not raw_name:
        return "Desconocido"
    name = str(raw_name).replace("_", " ").strip()
    fixes = {
        "Aimara": "Aymara",
        "Chileno_general": "Chileno general",
        "Chileno general": "Chileno general",
    }
    return fixes.get(name, name)


def _build_report_payload(user):
    profile = Profile.objects.filter(user=user).first()
    report_id = ensure_sample_code(profile) if profile else f"USR-{user.id:06d}"
    display_name = f"{user.first_name} {user.last_name}".strip() or user.username

    user_snps = UserSNP.objects.filter(user=user).select_related("snp")
    snp_list = [us.snp for us in user_snps if us.snp]
    extra_info_map = build_rsid_extra_info_map(snp_list)
    snps_analyzed = user_snps.count()

    areas = {
        key: {"total": 0, "counts": {"high": 0, "mid": 0, "low": 0}}
        for key in CATEGORY_ORDER
    }
    risk_counts = {"high": 0, "mid": 0, "low": 0, "neutral": 0}
    rsids = []

    country_counts = defaultdict(int)
    indigenous_counts = defaultdict(int)

    for user_snp in user_snps:
        snp = user_snp.snp
        if not snp:
            continue

        phenotype_name = (snp.fenotipo or "N/D").strip() or "N/D"
        extra_info = extra_info_map.get((snp.rsid, snp.genotipo, phenotype_name))
        freq_chile = None
        if extra_info and extra_info.freq_chile_percent is not None:
            try:
                freq_chile = float(extra_info.freq_chile_percent)
            except (TypeError, ValueError):
                freq_chile = None

        if snp.pais:
            country_counts[str(snp.pais).strip()] += 1
        if snp.pais and str(snp.pais).strip().lower() == "chile" and snp.poblacion_pais:
            indigenous_counts[str(snp.poblacion_pais).strip()] += 1

        category_key = _normalize_category(snp.categoria or snp.grupo)
        if not category_key:
            continue

        risk_key = _normalize_risk(snp.nivel_riesgo)
        areas[category_key]["total"] += 1
        areas[category_key]["counts"][risk_key] += 1
        risk_counts[risk_key] += 1

        rsids.append(
            {
                "rsid": snp.rsid,
                "fenotipo": snp.fenotipo,
                "categoria": category_key,
                "grupo": snp.grupo,
                "genotipo": snp.genotipo,
                "riesgo": RISK_LABELS.get(risk_key, "Bajo"),
                "magnitudEfecto": float(snp.magnitud_efecto)
                if snp.magnitud_efecto is not None
                else None,
                "aleloReferencia": snp.alelo_referencia,
                "aleloAlternativo": snp.alelo_alternativo,
                "cromosoma": snp.cromosoma,
                "posicion": str(snp.posicion) if snp.posicion is not None else None,
                "fuente": snp.fuente_base_datos,
                "porcentajeChilenos": freq_chile,
                "phenotypeDescription": extra_info.phenotype_description if extra_info else None,
                "pais": snp.pais,
            }
        )

    ancestry_items = []
    total_country = sum(country_counts.values())
    for country, count in sorted(country_counts.items(), key=lambda x: x[1], reverse=True):
        pct = round((count / total_country) * 100, 2) if total_country else 0
        ancestry_items.append({"country": country, "pct": pct})

    if ancestry_items:
        total_pct = sum(item["pct"] for item in ancestry_items)
        if total_pct and abs(total_pct - 100.0) > 0.01:
            ancestry_items[0]["pct"] = round(ancestry_items[0]["pct"] + (100.0 - total_pct), 2)

    ancestry_top5 = ancestry_items[:5]
    ancestry_map = {item["country"]: item["pct"] for item in ancestry_items}

    indigenous_items = []
    total_indigenous = sum(indigenous_counts.values())
    for name, count in sorted(indigenous_counts.items(), key=lambda x: x[1], reverse=True):
        pct = round((count / total_indigenous) * 100, 2) if total_indigenous else 0
        indigenous_items.append(
            {
                "name": _normalize_indigenous_name(name),
                "percentage": pct,
                "variantCount": count,
            }
        )

    frontend_domain = getattr(settings, "FRONTEND_DOMAIN", "https://pds-kappa.vercel.app")

    payload = {
        "people": [
            {
                "name": display_name,
                "displayName": display_name,
                "reportId": report_id,
                "date": timezone.now().strftime("%d/%m/%Y"),
                "link": frontend_domain,
                "summary": {
                    "snpsAnalyzed": snps_analyzed,
                    "riskCounts": risk_counts,
                },
                "areas": areas,
                "ancestryTop5": ancestry_top5,
                "ancestryMap": ancestry_map,
                "indigenousData": indigenous_items,
                "rsids": rsids,
            }
        ]
    }
    return payload


class UserReportPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        payload = _build_report_payload(user)

        report_generator_dir = None
        script_path = None
        candidate_dirs = []
        env_dir = os.environ.get("REPORT_GENERATOR_DIR")
        if env_dir:
            candidate_dirs.append(Path(env_dir))
        candidate_dirs.extend([
            settings.BASE_DIR / "report-generator",
            settings.BASE_DIR.parent / "report-generator",
            settings.BASE_DIR.parent.parent / "report-generator",
        ])

        for candidate in candidate_dirs:
            candidate_path = candidate / "generate.js"
            if candidate_path.exists():
                report_generator_dir = candidate
                script_path = candidate_path
                break

        if not script_path:
            return HttpResponse("Report generator no encontrado", status=500)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "report-data.json"
            output_dir = tmp_path / "out"
            manifest_path = tmp_path / "manifest.json"
            output_dir.mkdir(parents=True, exist_ok=True)

            input_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            cmd = [
                "node",
                str(script_path),
                "--input",
                str(input_path),
                "--out-dir",
                str(output_dir),
                "--manifest",
                str(manifest_path),
            ]

            result = subprocess.run(
                cmd,
                cwd=str(report_generator_dir),
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Error al generar PDF"
                return HttpResponse(f"Error al generar PDF: {error_msg}", status=500)

            if not manifest_path.exists():
                return HttpResponse("No se genero el manifiesto del reporte", status=500)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            reports = manifest.get("reports", [])
            if not reports:
                return HttpResponse("Manifiesto de reporte vacio", status=500)

            files = reports[0].get("files", [])
            if not files:
                return HttpResponse("No se encontraron PDFs para combinar", status=500)

            toc_entries = reports[0].get("tocEntries", [])
            target_pages = {}
            index_page_index = None
            page_index = 0

            writer = PdfWriter()
            for file_path in files:
                reader = PdfReader(str(file_path))
                filename = Path(file_path).name

                if filename.endswith("_indice.pdf"):
                    index_page_index = page_index

                target_key = _target_key_for_file(filename)
                if target_key and target_key not in target_pages:
                    target_pages[target_key] = page_index

                for page in reader.pages:
                    writer.add_page(page)

                page_index += len(reader.pages)

            # OPTIMIZATION: Skipping TOC Link generation to reduce processing time (~5-10s saved).
            # The visual TOC remains, but links are not clickable.
            # if toc_entries and index_page_index is not None:
            #     for row_index, entry in enumerate(toc_entries):
            #         target_key = entry.get("target")
            #         target_page_index = target_pages.get(target_key)
            #         if target_page_index is None:
            #             continue
            #         rect = _toc_link_rect(row_index)
            #         link = Link(rect=rect, target_page_index=target_page_index, border=[0, 0, 0])
            #         writer.add_annotation(index_page_index, link)

            merged_buffer = BytesIO()
            writer.write(merged_buffer)

            filename = f"Reporte_Genetico_{payload['people'][0]['reportId']}.pdf"
            response = HttpResponse(merged_buffer.getvalue(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
