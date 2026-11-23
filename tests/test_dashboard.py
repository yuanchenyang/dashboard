import json

import pytest
import requests
from bs4 import BeautifulSoup as RealBeautifulSoup

import dashboard
import utils


class FakeResponse:
    def __init__(self, content=b'', status_code=200, json_data=None):
        self.content = content
        self.status_code = status_code
        self.json_data = json_data
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self.json_data

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset:offset + chunk_size]


def test_meteoblue_parser_is_bounded_and_always_decomposed(monkeypatch):
    response = FakeResponse(b'<html><div id="blooimage" data-href="https://img"></div></html>')
    soup = RealBeautifulSoup(response.content, 'html.parser')
    original_decompose = soup.decompose
    decomposed = []

    def decompose():
        decomposed.append(True)
        original_decompose()

    soup.decompose = decompose
    parse_call = {}

    def make_soup(*args, **kwargs):
        parse_call['args'] = args
        parse_call['kwargs'] = kwargs
        return soup

    monkeypatch.setattr(utils.requests, 'get', lambda *args, **kwargs: response)
    monkeypatch.setattr(utils, 'BeautifulSoup', make_soup)

    assert utils.get_blooimage_src('/somewhere') == 'https://img'
    assert parse_call['args'][1] == utils.PARSER
    assert parse_call['kwargs']['parse_only'] is utils.METEOBLUE_PARSE_ONLY
    assert response.closed
    assert decomposed == [True]


def test_meteoblue_parser_decomposes_on_missing_image(monkeypatch):
    response = FakeResponse(b'<html><div>missing</div></html>')
    soup = RealBeautifulSoup(response.content, 'html.parser')
    original_decompose = soup.decompose
    decomposed = []

    def decompose():
        decomposed.append(True)
        original_decompose()

    soup.decompose = decompose
    monkeypatch.setattr(utils.requests, 'get', lambda *args, **kwargs: response)
    monkeypatch.setattr(utils, 'BeautifulSoup', lambda *args, **kwargs: soup)

    with pytest.raises(ValueError):
        utils.get_blooimage_src('/somewhere')
    assert decomposed == [True]


def test_pws_observation_uses_metric_json(monkeypatch):
    response = FakeResponse(json_data={'observations': [{
        'humidity': 75,
        'metric': {'temp': 20.25, 'windSpeed': 16.1},
    }]})
    request_call = {}

    def get(*args, **kwargs):
        request_call['args'] = args
        request_call['kwargs'] = kwargs
        return response

    monkeypatch.setattr(utils.requests, 'get', get)

    result = json.loads(utils.get_pws_observation('KTEST1', api_key='test-key'))

    assert result == {
        'temp': '20.2&deg;C', 'humidity': '75%', 'wind': '16 km/h'
    }
    assert request_call['args'] == (utils.PWS_OBSERVATIONS_URL,)
    assert request_call['kwargs'] == {
        'params': {
            'stationId': 'KTEST1',
            'format': 'json',
            'units': 'm',
            'numericPrecision': 'decimal',
            'apiKey': 'test-key',
        },
        'timeout': utils.TIMEOUT,
    }
    assert response.closed


def test_pws_no_content_returns_na(monkeypatch):
    response = FakeResponse(status_code=204)
    monkeypatch.setattr(utils.requests, 'get', lambda *args, **kwargs: response)

    result = json.loads(utils.get_pws_observation('KTEST1', api_key='test-key'))

    assert result == {'temp': 'N/A', 'humidity': 'N/A', 'wind': 'N/A'}
    assert response.closed


def pws_page(unit='e', status='connected', temp='61', humidity='64',
             wind='2.5'):
    def widget(tag, attr, value):
        return ('<{0} data-pws-id="KTEST1" data-status="{1}" data-unit="{2}" '
                '{3}="{4}" class="widget-view"></{0}>').format(
                    tag, status, unit, attr, value)
    return ('<html><body>' +
            widget('temp-widget-view', 'data-temp', temp) +
            widget('humidity-widget-view', 'data-humidity', humidity) +
            widget('wind-widget-view', 'data-wind-speed', wind) +
            '</body></html>').encode('utf-8')


@pytest.fixture
def no_weather_api_key(monkeypatch):
    monkeypatch.delenv('WEATHER_API_KEY', raising=False)


def test_pws_dashboard_widgets_are_converted_to_metric(monkeypatch,
                                                       no_weather_api_key):
    response = FakeResponse(content=pws_page(temp='68', humidity='64',
                                             wind='10'))
    calls = []

    def get(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    monkeypatch.setattr(utils.requests, 'get', get)

    result = json.loads(utils.get_pws_observation('ktest1'))

    assert result == {'temp': '20.0&deg;C', 'humidity': '64%',
                      'wind': '16 km/h'}
    assert calls == [((utils.WUNDERGROUND_PWS_URL.format('KTEST1'),), {
        'headers': utils.WUNDERGROUND_HEADERS,
        'timeout': utils.TIMEOUT,
        'stream': True,
    })]
    assert response.closed


@pytest.mark.parametrize('unit,expected_wind', [('m', '10 km/h'),
                                                ('h', '16 km/h'),
                                                ('s', '36 km/h')])
def test_pws_dashboard_widgets_handle_unit_systems(monkeypatch,
                                                   no_weather_api_key,
                                                   unit, expected_wind):
    response = FakeResponse(content=pws_page(unit=unit, temp='20',
                                             wind='10'))
    monkeypatch.setattr(utils.requests, 'get', lambda *a, **k: response)

    result = json.loads(utils.get_pws_observation('KTEST1'))

    assert result['temp'] == '20.0&deg;C'
    assert result['wind'] == expected_wind


def test_pws_offline_station_returns_na(monkeypatch, no_weather_api_key):
    response = FakeResponse(content=pws_page(status='offline', temp='',
                                             humidity='', wind=''))
    monkeypatch.setattr(utils.requests, 'get', lambda *a, **k: response)

    result = json.loads(utils.get_pws_observation('KTEST1'))

    assert result == {'temp': 'N/A', 'humidity': 'N/A', 'wind': 'N/A'}


def test_pws_layout_change_raises(monkeypatch, no_weather_api_key):
    response = FakeResponse(content=b'<html><body>redesigned</body></html>')
    monkeypatch.setattr(utils.requests, 'get', lambda *a, **k: response)

    with pytest.raises(ValueError, match='no data-temp'):
        utils.get_pws_observation('KTEST1')


def test_pws_rejects_invalid_station_id():
    with pytest.raises(ValueError, match='Invalid PWS station ID'):
        utils.get_pws_observation('../etc')


def test_pws_dashboard_response_has_a_size_limit(monkeypatch,
                                                 no_weather_api_key):
    response = FakeResponse(content=b'x' * 11)
    monkeypatch.setattr(utils, 'PWS_PAGE_MAX_BYTES', 10)
    monkeypatch.setattr(utils.requests, 'get', lambda *args, **kwargs: response)

    with pytest.raises(ValueError, match='size limit'):
        utils.get_pws_observation('KTEST1')
    assert response.closed


def test_mf_table_matches_custom_element(monkeypatch):
    page = (b'<html><head></head><body><fc-forecast-table '
            b'class="js-vis-forecast forecast-table" id="forecast-table">'
            b'<table><tr><td><img src="/x.png"></td></tr></table>'
            b'</fc-forecast-table></body></html>')
    monkeypatch.setattr(utils.requests, 'get',
                        lambda *a, **k: FakeResponse(content=page))

    data = utils.get_mf_table('Some-Peak/forecasts/1000')

    assert data['forecast_html'].startswith('<fc-forecast-table')
    assert 'src="{}/x.png"'.format(utils.MF_BASE) in data['forecast_html']


def test_mf_missing_table_raises(monkeypatch):
    page = b'<html><head></head><body>nothing</body></html>'
    monkeypatch.setattr(utils.requests, 'get',
                        lambda *a, **k: FakeResponse(content=page))

    with pytest.raises(ValueError, match='no forecast table'):
        utils.get_mf_table('Some-Peak/forecasts/1000')


def test_pws_http_error_does_not_expose_configured_key(monkeypatch):
    api_key = '1234567890abcdef1234567890abcdef'
    response = FakeResponse(status_code=401)
    monkeypatch.setattr(utils.requests, 'get', lambda *args, **kwargs: response)

    with pytest.raises(requests.HTTPError) as error:
        utils.get_pws_observation('KTEST1', api_key=api_key)

    assert str(error.value) == 'PWS API returned HTTP 401'
    assert api_key not in str(error.value)


def test_weather_timeout_returns_na_without_a_500(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout('upstream timed out')

    monkeypatch.setattr(dashboard, 'get_pws_observation', timeout)
    response = dashboard.app.test_client().get('/get_pws?id=timeout-test')

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {
        'temp': 'N/A', 'humidity': 'N/A', 'wind': 'N/A'
    }


def test_bluebikes_timeout_returns_na_without_a_500(monkeypatch):
    class TimeoutClient:
        def __init__(self):
            raise requests.Timeout('upstream timed out')

    monkeypatch.setattr(dashboard, 'GBFSStationClient', TimeoutClient)
    response = dashboard.app.test_client().get(
        '/get_bluebikes?station_ids=one,two')

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {
        'one': {'num_bikes_available': 'N.A.', 'num_docks_available': 'N.A.'},
        'two': {'num_bikes_available': 'N.A.', 'num_docks_available': 'N.A.'},
    }
