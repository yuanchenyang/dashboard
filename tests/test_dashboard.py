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


@pytest.fixture
def pws_key_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / 'weather-api-key'
    monkeypatch.setattr(utils, 'PWS_API_KEY_CACHE_FILE', str(cache_path))
    monkeypatch.setattr(utils, '_pws_api_key', None)
    monkeypatch.delenv('WEATHER_API_KEY', raising=False)
    return cache_path


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


def test_pws_key_is_discovered_and_persisted(monkeypatch, pws_key_cache):
    browser_key = '1234567890abcdef1234567890abcdef'
    unrelated_key = 'abcdef1234567890abcdef1234567890'
    page = (
        b'https://api.weather.com/v3/wx/forecast?apiKey=' +
        unrelated_key.encode('ascii') +
        b' https://api.weather.com/v2/pws/observations/current?apiKey=' +
        browser_key.encode('ascii') + b'&stationId=KTEST1')
    response = FakeResponse(content=page)
    calls = []

    def get(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    monkeypatch.setattr(utils.requests, 'get', get)

    assert utils.get_pws_api_key('KTEST1') == browser_key
    assert pws_key_cache.read_text() == browser_key
    assert response.closed
    assert calls == [((utils.WUNDERGROUND_PWS_URL.format('KTEST1'),), {
        'headers': utils.WUNDERGROUND_HEADERS,
        'timeout': utils.TIMEOUT,
        'stream': True,
    })]

    monkeypatch.setattr(utils, '_pws_api_key', None)
    assert utils.get_pws_api_key('KTEST1') == browser_key
    assert len(calls) == 1


def test_pws_stale_key_is_refreshed_once(monkeypatch, pws_key_cache):
    stale_key = '00000000000000000000000000000000'
    current_key = '1234567890abcdef1234567890abcdef'
    pws_key_cache.write_text(stale_key)
    discovery_page = (
        b'https://api.weather.com/v2/pws/observations/current?apiKey=' +
        current_key.encode('ascii'))
    api_keys = []
    discovery_calls = []

    def get(url, **kwargs):
        if url == utils.WUNDERGROUND_PWS_URL.format('KTEST1'):
            discovery_calls.append(url)
            return FakeResponse(content=discovery_page)
        api_key = kwargs['params']['apiKey']
        api_keys.append(api_key)
        if api_key == stale_key:
            return FakeResponse(status_code=401)
        return FakeResponse(json_data={'observations': [{
            'humidity': 61,
            'metric': {'temp': 19.5, 'windSpeed': 8.2},
        }]})

    monkeypatch.setattr(utils.requests, 'get', get)

    result = json.loads(utils.get_pws_observation('KTEST1'))

    assert result == {
        'temp': '19.5&deg;C', 'humidity': '61%', 'wind': '8 km/h'
    }
    assert api_keys == [stale_key, current_key]
    assert discovery_calls == [utils.WUNDERGROUND_PWS_URL.format('KTEST1')]
    assert pws_key_cache.read_text() == current_key


def test_pws_discovery_response_has_a_size_limit(monkeypatch, pws_key_cache):
    response = FakeResponse(content=b'x' * 11)
    monkeypatch.setattr(utils, 'PWS_PAGE_MAX_BYTES', 10)
    monkeypatch.setattr(utils.requests, 'get', lambda *args, **kwargs: response)

    with pytest.raises(ValueError, match='size limit'):
        utils.get_pws_api_key('KTEST1')
    assert response.closed


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
