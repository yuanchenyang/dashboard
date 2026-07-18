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


def test_pws_requires_configured_api_key(monkeypatch):
    monkeypatch.delenv('WEATHER_API_KEY', raising=False)

    with pytest.raises(RuntimeError, match='WEATHER_API_KEY'):
        utils.get_pws_observation('KTEST1')


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
