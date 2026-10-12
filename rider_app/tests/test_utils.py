from unittest import mock

import requests
from django.conf import settings
from django.test import SimpleTestCase

from rider_app.utils import calculate_osrm_distance


class CalculateOsrmDistanceTests(SimpleTestCase):
    EQUATOR_DEGREE_KM = 111.19

    def route_response(self, meters, status_code=200):
        response = mock.MagicMock()
        response.status_code = status_code
        response.json.return_value = {
            'code': 'Ok',
            'routes': [{'distance': meters}],
        }
        return response

    def equator_call(self, response=None, side_effect=None):
        with mock.patch(
            'rider_app.utils.requests.get',
            return_value=response,
            side_effect=side_effect,
        ):
            return calculate_osrm_distance(0.0, 0.0, 0.0, 1.0)

    def json_response(self, payload):
        response = mock.MagicMock()
        response.json.return_value = payload
        return response

    def test_request_url_and_timeout_are_exact(self):
        with mock.patch(
            'rider_app.utils.requests.get',
            return_value=self.route_response(1000),
        ) as get:
            calculate_osrm_distance(12.9, 77.6, 13.0, 77.7)

        expected_url = (
            f"{settings.OSRM_SERVER_URL}/route/v1/driving/77.6,12.9;77.7,13.0"
            "?overview=false"
        )
        self.assertEqual(get.call_args, mock.call(expected_url, timeout=10))

    def test_successful_route_returns_distance_in_kilometres(self):
        result = self.equator_call(self.route_response(4123.4))
        self.assertEqual(result, 4.12)

    def test_zero_metre_route_returns_zero(self):
        result = self.equator_call(self.route_response(0))
        self.assertEqual(result, 0.0)

    def test_non_200_response_with_ok_body_still_returns_route(self):
        result = self.equator_call(self.route_response(2500, status_code=500))
        self.assertEqual(result, 2.5)

    def test_non_ok_status_code_falls_back_to_haversine(self):
        response = self.json_response({'code': 'NoRoute', 'routes': []})
        with self.assertLogs('rider_app.utils', level='WARNING'):
            result = self.equator_call(response)
        self.assertEqual(result, self.EQUATOR_DEGREE_KM)

    def test_empty_route_list_falls_back_to_haversine(self):
        response = self.json_response({'code': 'Ok', 'routes': []})
        with self.assertLogs('rider_app.utils', level='WARNING'):
            result = self.equator_call(response)
        self.assertEqual(result, self.EQUATOR_DEGREE_KM)

    def test_missing_routes_key_falls_back_to_haversine(self):
        response = self.json_response({'code': 'Ok'})
        with self.assertLogs('rider_app.utils', level='ERROR'):
            result = self.equator_call(response)
        self.assertEqual(result, self.EQUATOR_DEGREE_KM)

    def test_malformed_json_falls_back_to_haversine(self):
        response = mock.MagicMock()
        response.json.side_effect = ValueError('Expecting value: line 1')
        with self.assertLogs('rider_app.utils', level='ERROR'):
            result = self.equator_call(response)
        self.assertEqual(result, self.EQUATOR_DEGREE_KM)

    def test_request_timeout_falls_back_to_haversine(self):
        with self.assertLogs('rider_app.utils', level='ERROR'):
            result = self.equator_call(
                side_effect=requests.exceptions.Timeout('too slow')
            )
        self.assertEqual(result, self.EQUATOR_DEGREE_KM)
