import requests
from bs4 import BeautifulSoup
from gbfs.client import GBFSClient

class GBFSStationClient(GBFSClient):
    def __init__(self, url, language=None, json_fetcher=None):
        GBFSClient.__init__(self, url, language, json_fetcher)
        station_information = self.request_feed('station_information')
        self.stations = {s['station_id']: s
                         for s in station_information['data']['stations']}

    def get_stations(self):
        for s in self.request_feed('station_status')['data']['stations']:
            self.stations[s['station_id']].update(s)
        return self.stations

# Use this otherwise webpage returns browser unsupported error
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
COOKIES = {'precip': 'MILLIMETER',
           'speed': 'KILOMETER_PER_HOUR',
           'temp': 'CELSIUS'}

def get_blooimage_src(url):
    res = requests.get(url, headers=HEADERS, cookies=COOKIES)
    soup = BeautifulSoup(res.text, features="html5lib")
    return soup.find(id='blooimage').find('img')['data-original']