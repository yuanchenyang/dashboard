import json

import pytest

import dashboard
from tests.page_endpoints import (assert_endpoint_payload, endpoint_paths,
                                  endpoints_from_page)


EXPECTED_ENDPOINTS = {
    'cam_nh': {
        '/get_bkb', '/get_bluebikes', '/get_meteoblue',
        '/get_sailing_weather', '/get_trash', '/get_weatherstory',
        '/get_pws',
    },
    'charles126': {
        '/get_bkb', '/get_bluebikes', '/get_meteoblue',
        '/get_sailing_weather', '/get_trash', '/get_weatherstory',
        '/get_pws',
    },
    'western322': {
        '/get_bkb', '/get_bluebikes', '/get_meteoblue',
        '/get_sailing_weather', '/get_trash', '/get_weatherstory',
        '/get_pws',
    },
    'brookline214': {
        '/get_bluebikes', '/get_meteoblue', '/get_nextbus',
        '/get_sailing_weather', '/get_trash', '/get_weatherstory',
        '/get_pws',
    },
    'ne-climbing': {
        '/get_meteoblue', '/get_mf', '/get_pws',
    },
}


@pytest.fixture
def fake_upstreams(monkeypatch):
    class StationMap(dict):
        def __missing__(self, station_id):
            station = {
                'legacy_id': station_id,
                'num_bikes_available': 4,
                'num_docks_available': 8,
            }
            self[station_id] = station
            return station

    class FakeGBFSStationClient:
        def get_stations(self):
            return StationMap()

    weather = json.dumps({
        'temp': '20.0&deg;C', 'humidity': '50%', 'wind': '5 km/h'
    })
    monkeypatch.setattr(dashboard, 'GBFSStationClient', FakeGBFSStationClient)
    monkeypatch.setattr(dashboard, 'get_pws_observation', lambda station_id: weather)
    monkeypatch.setattr(dashboard, 'scrape_sailing_weather', lambda: weather)
    monkeypatch.setattr(
        dashboard, 'get_blooimage_src',
        lambda url: '//my.meteoblue.com/images/test?location=' + url)
    monkeypatch.setattr(dashboard, 'get_nws_weatherstory',
                        lambda wfo: ['https://weather.gov/{}/story.png'.format(wfo)])
    monkeypatch.setattr(dashboard, 'get_next_bus_info', lambda stopid: json.dumps({
        'title': 'Route', 'arrivals': '5 mins'
    }))
    monkeypatch.setattr(dashboard, 'get_trash_info', lambda placeid: json.dumps({
        'title': 'Trash', 'datestr': 'Mon Jul 20', 'items': 'Trash'
    }))
    monkeypatch.setattr(dashboard, 'get_bkb_routesetting', lambda cal_id: json.dumps({
        'datestr': 'Mon Jul 20', 'items': 'Setting'
    }))
    monkeypatch.setattr(dashboard, 'get_mf_table', lambda url: {
        'mf_styles': '',
        'mf_config': '',
        'mf_scripts': '',
        'forecast_html': '<div class="forecast-table">Forecast</div>',
    })


@pytest.mark.parametrize('page_id', EXPECTED_ENDPOINTS)
def test_every_server_endpoint_used_by_page_loads(page_id, fake_upstreams):
    with dashboard.app.test_client() as client:
        page = client.get('/?page_id=' + page_id)
        assert page.status_code == 200

        endpoints = endpoints_from_page(page.get_data(as_text=True))
        assert endpoint_paths(endpoints) == EXPECTED_ENDPOINTS[page_id]

        for endpoint in endpoints:
            assert_endpoint_payload(endpoint, client.get(endpoint))


def test_ne_climbing_uses_selected_replacement_stations(fake_upstreams):
    with dashboard.app.test_client() as client:
        page = client.get('/?page_id=ne-climbing').get_data(as_text=True)

    assert '/get_pws?id=KMAERVIN18' in page
    assert '/get_pws?id=KNYNEWPA101' in page
    assert 'KMAERVIN9' not in page
    assert 'KNYNEWPA71' not in page
