import os

import pytest


# Mock network classes

class dummy_requests_module:
    def __init__(self, response):
        self._response = response
        self.calls = []
    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self._response


class dummy_response_csv_200:
    status_code = 200
    closed = False
    def iter_lines(self, *args, **kwargs):
        yield 'Country Code,Name,Location,System ID,URL,Auto-Discovery URL'
        yield 'AE,ADCB Bikeshare,"Abu Dhabi, AE",ABU,https://www.bikeshare.ae/,https://api-core.bikeshare.ae/gbfs/gbfs.json'
    def close(self):
        self.closed = True


class dummy_response_csv_404:
    status_code = 404
    closed = False
    def iter_lines(self, *ars, **kwargs):
        yield '404: Not Found'
    def close(self):
        self.closed = True


class dummy_response_json:
    status_code = 200
    closed = False
    def json(self):
        return {'last_updated': 1543720674, 'ttl': 10, 'data': {'en': {'feeds': [{'name': 'station_status', 'url': 'https://api-core.bikeshare.ae/gbfs/en/station_status.json'}]}}}
    def close(self):
        self.closed = True


def test_local_csv_fetcher():
    from gbfs.const import gbfs_systems_csv_local_filepath
    from gbfs.data.fetchers import LocalCSVFetcher

    fetcher = LocalCSVFetcher()

    assert fetcher.fetch(gbfs_systems_csv_local_filepath)


def test_remote_csv_fetcher_400():
    from gbfs.const import gbfs_systems_csv_remote_url
    from gbfs.data.fetchers import RemoteCSVFetcher, REQUEST_TIMEOUT

    response = dummy_response_csv_200()
    requests_module = dummy_requests_module(response)
    fetcher = RemoteCSVFetcher(requests_module=requests_module)

    assert fetcher.fetch(gbfs_systems_csv_remote_url)
    assert requests_module.calls == [((gbfs_systems_csv_remote_url,),
                                      {'timeout': REQUEST_TIMEOUT})]
    assert response.closed


def test_remote_csv_fetcher_404():
    from gbfs.const import gbfs_systems_csv_remote_url
    from gbfs.data.fetchers import RemoteCSVFetcher

    response = dummy_response_csv_404()
    fetcher = RemoteCSVFetcher(requests_module=dummy_requests_module(response))

    with pytest.raises(RuntimeError):
        fetcher.fetch(gbfs_systems_csv_remote_url)
    assert response.closed


def test_local_json_fetcher():
    from gbfs.const import package_tests_fixtures_dirpath
    from gbfs.data.fetchers import LocalJSONFetcher

    fetcher = LocalJSONFetcher()

    assert fetcher.fetch(os.path.join(package_tests_fixtures_dirpath, 'gbfs.json'))


def test_remote_json_fetcher():
    from gbfs.data.fetchers import RemoteJSONFetcher, REQUEST_TIMEOUT

    response = dummy_response_json()
    requests_module = dummy_requests_module(response)
    fetcher = RemoteJSONFetcher(requests_module=requests_module)

    assert fetcher.fetch('http://path/to/gbfs.json')
    assert requests_module.calls == [(('http://path/to/gbfs.json',),
                                      {'timeout': REQUEST_TIMEOUT})]
    assert response.closed
