from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.models import Case, When, IntegerField
from accounts.authentication import JWTAuthentication
from .models import SNP, UserSNP
from profiles.models import Profile, ServiceStatus
from accounts.email_utils import send_results_ready_email
from accounts.roles import is_admin_or_analyst
import logging
import json

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class UploadGeneticFileAPIView(APIView):
    """Vista para procesar archivos genéticos y crear asociaciones user-snp"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Verificar que el usuario sea staff o analista autorizado
        if not is_admin_or_analyst(request.user):
            return Response(
                {"error": "No tienes permisos para realizar esta acción"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            # Obtener datos del body (JSON)
            try:
                data = json.loads(request.body or '{}')
            except json.JSONDecodeError:
                data = {}

            user_id = data.get('userId')
            file_content = data.get('fileContent', '').strip()
            filename = data.get('filename', 'report.txt').strip()

            # Validaciones
            if not user_id:
                return Response(
                    {"error": "userId es obligatorio"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not file_content:
                return Response(
                    {"error": "fileContent es obligatorio"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verificar que el usuario exista
            try:
                target_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "Usuario no encontrado"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Validar que el filename coincida con el sample_code del usuario
            try:
                user_profile = target_user.profile
                sample_code = user_profile.sample_code
                
                # Comparar: el filename (sin extensión) debe coincidir con el sample_code
                filename_without_ext = filename.split('.')[0]
                if filename_without_ext != sample_code:
                    return Response(
                        {
                            "error": "El nombre del archivo no coincide con el SampleCode del usuario."
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Profile.DoesNotExist:
                return Response(
                    {"error": "El usuario no tiene perfil configurado"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Procesar archivo genético
            processing_result = self._process_genetic_file(target_user, file_content)

            if not isinstance(processing_result, dict):
                return Response(
                    {"error": "Error al procesar el archivo genético"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Actualizar el service_status del usuario a COMPLETED y guardar nombre del archivo
            try:
                from django.utils import timezone
                profile, created = Profile.objects.get_or_create(user=target_user)
                profile.service_status = ServiceStatus.COMPLETED
                profile.report_filename = filename
                profile.report_uploaded_at = timezone.now()
                profile.save()
                logger.info(
                    f"Service status actualizado a COMPLETED para usuario {target_user.email}. "
                    f"Archivo: {filename}"
                )
            except Exception as e:
                logger.error(f"Error actualizando service_status: {str(e)}")

            # Enviar email de notificación al usuario
            user_name = (
                target_user.first_name
                or target_user.username
                or target_user.email.split('@')[0]
            )
            email_sent = False
            try:
                email_sent = send_results_ready_email(target_user.email, user_name)
                if email_sent:
                    logger.info(f"Email de resultados listos enviado a {target_user.email}")
                else:
                    logger.warning(
                        f"No se pudo enviar email de notificación a {target_user.email}"
                    )
            except Exception as e:
                logger.error(f"Error enviando email de notificación: {str(e)}")

            return Response({
                "success": True,
                "message": (
                    f"Archivo procesado. {processing_result['snps_added']} nuevas variantes "
                    f"genéticas agregadas."
                ),
                "user_id": user_id,
                "snps_count": processing_result['snps_added'],
                "status_updated": True,
                "email_sent": email_sent,
                "details": {
                    "total_lines": processing_result['total_lines'],
                    "processed_rsids": processing_result['processed_rsids'],
                    "unprocessed_lines": processing_result['unprocessed_lines'],
                    "skipped_lines": processing_result['snps_skipped'],
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error en UploadGeneticFileAPIView: {str(e)}", exc_info=True)
            return Response(
                {"error": "Error interno del servidor"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _process_genetic_file(self, user, file_content):
        """
        Procesa el contenido del archivo genético y crea asociaciones user-snp.
        - Normaliza genotipos (p.ej. T/C -> C/T).
        - Maneja SNPs duplicados usando filter().first() en vez de get().
        """
        try:
            lines = file_content.strip().split('\n')
            logger.info(f"Total de líneas en archivo: {len(lines)}")

            if not lines:
                logger.warning("Archivo vacío")
                return {
                    'snps_added': 0,
                    'snps_skipped': 0,
                    'total_lines': 0,
                    'processed_rsids': [],
                    'unprocessed_lines': []
                }

            snps_added = 0
            snps_skipped = 0
            processed_rsids = []
            unprocessed_lines = []

            for idx, line in enumerate(lines):
                if not line.strip():
                    continue

                parts = line.strip().split(',')

                if len(parts) < 3:
                    logger.warning(
                        f"Línea {idx+1}: formato incompleto. Contenido: {line}"
                    )
                    unprocessed_lines.append({
                        "line": idx + 1,
                        "content": line,
                        "reason": "Formato incompleto"
                    })
                    snps_skipped += 1
                    continue

                cromosoma = parts[0].strip()
                rsid = parts[1].strip()
                genotipo = parts[2].strip()

                if not cromosoma or not rsid or not genotipo:
                    logger.warning(
                        f"Línea {idx+1}: campos vacíos. Contenido: {line}"
                    )
                    unprocessed_lines.append({
                        "line": idx + 1,
                        "content": line,
                        "reason": "Campos vacíos"
                    })
                    snps_skipped += 1
                    continue

                # Normalizar genotipo (ordenar alelos, p.ej. T/C -> C/T)
                genotipo_normalizado = genotipo
                if '/' in genotipo:
                    alelos = [a.strip() for a in genotipo.split('/') if a.strip()]
                    alelos.sort()
                    genotipo_normalizado = "/".join(alelos)

                try:
                    # Buscar SNPs que coincidan con el rsid y el genotipo normalizado
                    snp_qs = SNP.objects.filter(rsid=rsid, genotipo=genotipo_normalizado)

                    # Priorizar registros con informaciИn de Chile (evita que se asigne Finlandia u otro paЦs
                    # cuando el SNP tiene varias filas con el mismo rsid/genotipo).
                    priority_order = Case(
                        When(pais__iexact='Chile', then=0),
                        When(continente__icontains='america', then=1),
                        When(poblacion_pais__isnull=False, then=2),
                        When(pais__isnull=False, then=3),
                        default=4,
                        output_field=IntegerField()
                    )
                    snp_qs = snp_qs.annotate(priority=priority_order).order_by('priority', '-af_pais', 'id')

                    if not snp_qs.exists():
                        logger.warning(
                            f"Línea {idx+1}: SNP no encontrado en BD (rsid={rsid}, "
                            f"genotipo={genotipo} -> normalizado={genotipo_normalizado})."
                        )
                        unprocessed_lines.append({
                            "line": idx + 1,
                            "content": line,
                            "reason": "SNP no encontrado en la base de datos"
                        })
                        snps_skipped += 1
                        continue

                    if snp_qs.count() > 1:
                        logger.warning(
                            f"Línea {idx+1}: SNP con rsid={rsid}, genotipo={genotipo_normalizado} "
                            f"tiene {snp_qs.count()} registros. Usando el primero."
                        )

                    snp = snp_qs.first()
                    processed_rsids.append(rsid)
                    logger.debug(
                        f"SNP encontrado en BD: rsid={rsid}, "
                        f"genotipo_original={genotipo}, genotipo_normalizado={genotipo_normalizado}"
                    )

                    # Crear asociación usuario-SNP
                    user_snp, created = UserSNP.objects.get_or_create(
                        user=user,
                        snp=snp
                    )
                    if created:
                        snps_added += 1
                        logger.debug(
                            f"Asociación user-snp creada: user={user.id}, "
                            f"rsid={rsid}, genotipo={genotipo_normalizado}"
                        )
                    else:
                        logger.debug(
                            f"Asociación user-snp ya existía: user={user.id}, "
                            f"rsid={rsid}, genotipo={genotipo_normalizado}"
                        )

                except Exception as snp_error:
                    logger.error(
                        f"Error procesando SNP en línea {idx+1}: {str(snp_error)}",
                        exc_info=True
                    )
                    unprocessed_lines.append({
                        "line": idx + 1,
                        "content": line,
                        "reason": str(snp_error)
                    })
                    snps_skipped += 1

            result = {
                'snps_added': snps_added,
                'snps_skipped': snps_skipped,
                'total_lines': len(lines),
                'processed_rsids': processed_rsids,
                'unprocessed_lines': unprocessed_lines
            }
            logger.info(f"Procesamiento completado: {result}")
            return result

        except Exception as e:
            logger.error(
                f"Error procesando archivo genético: {str(e)}",
                exc_info=True
            )
            return -1



@method_decorator(csrf_exempt, name='dispatch')
class DeleteGeneticFileAPIView(APIView):
    """Vista para eliminar reportes genéticos de un usuario"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Verificar que el usuario sea staff o analista autorizado
        if not is_admin_or_analyst(request.user):
            return Response(
                {"error": "No tienes permisos para realizar esta acción"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            # Obtener datos del body
            try:
                data = json.loads(request.body or '{}')
            except json.JSONDecodeError:
                data = {}

            user_id = data.get('userId')

            if not user_id:
                return Response(
                    {"error": "userId es obligatorio"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verificar que el usuario exista
            try:
                target_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "Usuario no encontrado"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Eliminar todas las asociaciones user-snp del usuario
            deleted_count, _ = UserSNP.objects.filter(user=target_user).delete()
            logger.info(f"Eliminadas {deleted_count} variantes genéticas del usuario {target_user.email}")

            # Actualizar el service_status a NO_PURCHASED
            try:
                profile = target_user.profile
                profile.service_status = ServiceStatus.NO_PURCHASED
                profile.save()
                logger.info(f"Service status actualizado a NO_PURCHASED para usuario {target_user.email}")
            except Profile.DoesNotExist:
                logger.warning(f"El usuario {target_user.email} no tiene perfil")

            return Response({
                "success": True,
                "message": f"Reporte genético eliminado. {deleted_count} variantes removidas.",
                "user_id": user_id,
                "deleted_count": deleted_count
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error en DeleteGeneticFileAPIView: {str(e)}", exc_info=True)
            return Response(
                {"error": "Error interno del servidor"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class GetUserReportStatusAPIView(APIView):
    """Vista para obtener el estado de reportes de un usuario"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        # Verificar que el usuario sea staff
        if not is_admin_or_analyst(request.user):
            return Response(
                {"error": "No tienes permisos para realizar esta ación"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            # Verificar que el usuario exista
            try:
                target_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "Usuario no encontrado"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Verificar si tiene UserSNP
            has_snps = UserSNP.objects.filter(user=target_user).exists()
            snp_count = UserSNP.objects.filter(user=target_user).count()
            
            # Obtener el service_status y datos del archivo
            try:
                profile = target_user.profile
                service_status = profile.service_status
                report_filename = profile.report_filename
                report_uploaded_at = profile.report_uploaded_at.strftime("%Y-%m-%d") if profile.report_uploaded_at else None
            except Profile.DoesNotExist:
                service_status = ServiceStatus.NO_PURCHASED
                report_filename = None
                report_uploaded_at = None

            return Response({
                "user_id": user_id,
                "has_report": has_snps,
                "snp_count": snp_count,
                "service_status": service_status,
                "report_filename": report_filename,
                "report_date": report_uploaded_at
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error en GetUserReportStatusAPIView: {str(e)}", exc_info=True)
            return Response(
                {"error": "Error interno del servidor"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
