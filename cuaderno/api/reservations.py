"""Bounded reservation JSON contracts and authorized native workflow endpoints."""
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework import serializers
from rest_framework.response import Response
from cookbook.helper.permission_helper import CustomTokenHasReadWriteScope, has_group_permission
from cuaderno.api.base import CuadernoAPIView, CuadernoIsOperator
from cuaderno.api.prices import JsonIdentifierField
from cuaderno.api.production import StrictSerializer
from cuaderno.services.functional_access import page_window
from cuaderno.services.planning import require_professional
from cuaderno.services.reservations import (can_manage, can_operate, create_reservation, menu_choices, reservation_payload,
    reservation_summary, transition_reservation, update_reservation, visible_reservations)


class ReservationWriteSerializer(StrictSerializer):
    customer_name = serializers.CharField(max_length=160)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True, default='')
    service_date = serializers.DateField()
    service_time = serializers.TimeField(input_formats=['%H:%M'])
    template = JsonIdentifierField()
    template_day = serializers.IntegerField(min_value=0, max_value=34)
    meal_type = JsonIdentifierField()
    covers = JsonIdentifierField()
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    revision = JsonIdentifierField(required=False)
    reason = serializers.CharField(max_length=1000)

    def validate_covers(self, value):
        if value > 9999:
            raise serializers.ValidationError('Los comensales deben ser un entero entre 1 y 9999.')
        return value

    def validate_template_day(self, value):
        if type(self.initial_data.get('template_day')) is not int:
            raise serializers.ValidationError('El día debe ser un entero.')
        return value

    def validate(self, attrs):
        if not self.partial and not (attrs.get('phone') or attrs.get('email')):
            raise serializers.ValidationError({'contact': 'Indica teléfono o email.'})
        if self.partial and not attrs.get('revision'):
            raise serializers.ValidationError({'revision': 'Envía la revisión actual.'})
        if not attrs.get('reason'):
            raise serializers.ValidationError({'reason': 'Indica el motivo del cambio.'})
        return attrs


class ReservationTransitionSerializer(StrictSerializer):
    action = serializers.ChoiceField(choices=['confirm', 'start_kitchen', 'serve', 'cancel'])
    revision = JsonIdentifierField()
    reason = serializers.CharField(max_length=1000)


class ReservationResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    customer_name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.CharField()
    service_date = serializers.DateField()
    service_time = serializers.TimeField()
    template = serializers.IntegerField()
    template_name = serializers.CharField()
    template_day = serializers.IntegerField()
    meal_type = serializers.IntegerField()
    meal_type_name = serializers.CharField()
    covers = serializers.IntegerField()
    note = serializers.CharField()
    state = serializers.CharField()
    revision = serializers.IntegerField()
    menu_snapshot = serializers.JSONField()
    services = serializers.ListField(child=serializers.JSONField())
    history = serializers.ListField(child=serializers.JSONField(), required=False)
    can_operate = serializers.BooleanField()
    can_edit = serializers.BooleanField()
    can_change_menu = serializers.BooleanField()
    can_cancel = serializers.BooleanField()


class ReservationListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    offset = serializers.IntegerField()
    limit = serializers.IntegerField()
    results = ReservationResponseSerializer(many=True)
    can_operate = serializers.BooleanField()
    can_manage = serializers.BooleanField()


class ReservationMenusResponseSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.JSONField())


class ReservationSummaryResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    pending_covers = serializers.IntegerField()
    in_kitchen_covers = serializers.IntegerField()
    total_active_covers = serializers.IntegerField()
    groups = serializers.ListField(child=serializers.JSONField())


class ReservationDateSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)


class ReservationBaseView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]


class ReservationListView(ReservationBaseView):
    @extend_schema(operation_id='cuaderno_reservations_list', responses=ReservationListResponseSerializer, parameters=[
        OpenApiParameter('date', OpenApiTypes.DATE), OpenApiParameter('from_date', OpenApiTypes.DATE),
        OpenApiParameter('to_date', OpenApiTypes.DATE), OpenApiParameter('offset', OpenApiTypes.INT),
        OpenApiParameter('limit', OpenApiTypes.INT)])
    def get(self, request):
        require_professional(request.space)
        filters = ReservationDateSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        dates = filters.validated_data
        query = {}
        if 'date' in dates: query['service_date'] = dates['date']
        if 'from_date' in dates: query['service_date__gte'] = dates['from_date']
        if 'to_date' in dates: query['service_date__lte'] = dates['to_date']
        rows = visible_reservations(request, dates=query).order_by('service_date', 'service_time', 'pk')
        if 'date' in dates:
            rows = rows.filter(service_date=dates['date'])
        if 'from_date' in dates:
            rows = rows.filter(service_date__gte=dates['from_date'])
        if 'to_date' in dates:
            rows = rows.filter(service_date__lte=dates['to_date'])
        offset, limit = page_window(request)
        return Response({'count': rows.count(), 'offset': offset, 'limit': limit,
                         'results': [reservation_payload(request, row, detail=False) for row in rows[offset:offset + limit]],
                         'can_operate': can_operate(request), 'can_manage': can_manage(request)})

    @extend_schema(operation_id='cuaderno_reservation_create', request=ReservationWriteSerializer, responses={201: ReservationResponseSerializer})
    def post(self, request):
        serializer = ReservationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if 'revision' in data:
            raise serializers.ValidationError({'revision': 'Una nueva reserva no recibe revisión previa.'})
        row = create_reservation(request, data)
        return Response(reservation_payload(request, row), status=201)


class ReservationDetailView(ReservationBaseView):
    @extend_schema(operation_id='cuaderno_reservation_retrieve', responses=ReservationResponseSerializer)
    def get(self, request, reservation_id):
        require_professional(request.space)
        return Response(reservation_payload(request, get_object_or_404(visible_reservations(request, reservation_id=reservation_id), pk=reservation_id)))

    @extend_schema(operation_id='cuaderno_reservation_update', request=ReservationWriteSerializer, responses=ReservationResponseSerializer)
    def patch(self, request, reservation_id):
        serializer = ReservationWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        row = update_reservation(request, reservation_id, dict(serializer.validated_data))
        return Response(reservation_payload(request, row))


class ReservationTransitionView(ReservationBaseView):
    @extend_schema(operation_id='cuaderno_reservation_transition', request=ReservationTransitionSerializer, responses=ReservationResponseSerializer)
    def post(self, request, reservation_id):
        serializer = ReservationTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = transition_reservation(request, reservation_id, serializer.validated_data)
        return Response(reservation_payload(request, row))


class ReservationSummaryView(ReservationBaseView):
    @extend_schema(operation_id='cuaderno_reservations_summary', responses=ReservationSummaryResponseSerializer, parameters=[OpenApiParameter('date', OpenApiTypes.DATE, required=True)])
    def get(self, request):
        require_professional(request.space)
        field = serializers.DateField()
        service_date = field.run_validation(request.query_params.get('date'))
        return Response(reservation_summary(request, service_date))


class ReservationMenusView(ReservationBaseView):
    @extend_schema(operation_id='cuaderno_reservation_menus_list', responses=ReservationMenusResponseSerializer)
    def get(self, request):
        return Response({'results': menu_choices(request)})
