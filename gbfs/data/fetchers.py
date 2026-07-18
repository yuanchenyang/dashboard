import requests
import json

REQUEST_TIMEOUT = (3.05, 5)


class FileFetcher():
    def fetch(url):
        pass


class LocalCSVFetcher(FileFetcher):
    def fetch(self, url):
        with open(url, 'r') as f:
            data = f.readlines()
        return data


class RemoteCSVFetcher(FileFetcher):
    _requests_module = requests

    def __init__(self, requests_module=None, timeout=REQUEST_TIMEOUT):
        if requests_module:
            self._requests_module = requests_module
        self._timeout = timeout

        assert self._requests_module

    def fetch(self, url):
        response = self._requests_module.get(url, timeout=self._timeout)
        try:
            if response.status_code != 200:
                raise RuntimeError('HTTPS request for {} failed with status code {}' \
                                   .format(url, response.status_code))
            return list(response.iter_lines(decode_unicode=True))
        finally:
            close = getattr(response, 'close', None)
            if close:
                close()


class LocalJSONFetcher(FileFetcher):
    _json_module = json

    def __init__(self, json_module=None):
        if json_module:
            self._json_module = json_module
        assert self._json_module

    def fetch(self, url):
        with open(url, 'r') as f:
            data = self._json_module.load(f)
        return data


class RemoteJSONFetcher(FileFetcher):
    _requests_module = requests

    def __init__(self, requests_module=None, timeout=REQUEST_TIMEOUT):
        if requests_module:
            self._requests_module = requests_module
        self._timeout = timeout
        assert self._requests_module

    def fetch(self, url):
        response = self._requests_module.get(url, timeout=self._timeout)
        try:
            if response.status_code != 200:
                raise RuntimeError('HTTPS request for {} failed with status code {}' \
                                   .format(url, response.status_code))
            return response.json()
        finally:
            close = getattr(response, 'close', None)
            if close:
                close()
