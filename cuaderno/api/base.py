"""Common JSON envelope contract for Cuaderno API operations."""
from rest_framework.exceptions import ParseError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission, SAFE_METHODS
from cookbook.helper.permission_helper import has_group_permission


class CuadernoIsOperator(BasePermission):
    """Native groups: Consulta reads; Cocina and Responsable operate."""
    def has_permission(self, request, view):
        return has_group_permission(request, ['guest' if request.method in SAFE_METHODS else 'user'])


class ObjectJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type=media_type, parser_context=parser_context)
        if not isinstance(data, dict):
            raise ParseError('Envía un objeto JSON con los campos de la operación.')
        return data


class CuadernoAPIView(APIView):
    parser_classes = [ObjectJSONParser, FormParser, MultiPartParser]
