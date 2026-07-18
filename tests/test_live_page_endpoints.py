import os

import pytest

import dashboard
from tests.page_endpoints import assert_endpoint_payload, endpoints_from_page


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get('RUN_LIVE_ENDPOINT_TESTS') != '1' or
        not os.environ.get('WEATHER_API_KEY'),
        reason=('set RUN_LIVE_ENDPOINT_TESTS=1 and WEATHER_API_KEY to call '
                'external services'),
    ),
]


def test_live_endpoints_used_by_all_pages():
    endpoints = set()
    failures = []

    with dashboard.app.test_client() as client:
        for page in dashboard.available_pages:
            response = client.get('/?page_id=' + page.id)
            assert response.status_code == 200
            endpoints.update(endpoints_from_page(response.get_data(as_text=True)))

        for endpoint in sorted(endpoints):
            response = client.get(endpoint)
            try:
                assert_endpoint_payload(endpoint, response)
            except AssertionError as error:
                failures.append('{}: {}'.format(endpoint, error))

    assert not failures, '\n'.join(failures)
