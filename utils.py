import json
import requests
from bs4 import BeautifulSoup
from gbfs.client import GBFSClient

BLUEBIKE_GBFS = 'https://gbfs.bluebikes.com/gbfs/gbfs.json'
WUNDERGROUND_URL = 'https://www.wunderground.com/dashboard/pws'
METEOBLUE_URL = 'https://www.meteoblue.com/en/weather/'
SAILING_WEATHER_URL = 'http://sailing.mit.edu/weather/'
NEXTBUS_URL = 'https://retro.umoiq.com/service/publicJSONFeed'#'https://webservices.nextbus.com/service/publicJSONFeed'
TIMEOUT = 5

class GBFSStationClient(GBFSClient):
    def __init__(self, language=None, json_fetcher=None):
        GBFSClient.__init__(self, BLUEBIKE_GBFS, language, json_fetcher)
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
    res = requests.get(METEOBLUE_URL + url, headers=HEADERS, cookies=COOKIES, timeout=TIMEOUT)
    soup = BeautifulSoup(res.text, features="html5lib")
    return soup.find(id='blooimage').find('img')['data-original']

def scrape_wunderground(station_id):
    url = '{}/{}'.format(WUNDERGROUND_URL, station_id)
    soup = BeautifulSoup(requests.get(url, timeout=TIMEOUT).text, features="html5lib")
    vals = soup.find_all("span", attrs={'class': 'wu-value'})
    temp_F, humidity, wind_mph = [float(vals[i].text) for i in (0, 7, 2)]
    return weather_data_json(F_to_C(temp_F), humidity, mi_to_km(wind_mph))

def scrape_sailing_weather():
    soup = BeautifulSoup(requests.get(SAILING_WEATHER_URL, timeout=TIMEOUT).text,
                         features="html5lib")
    temp_F, humidity, wind_mph = [float(soup.find("a", attrs={'href': val}).text)
                                  for val in ('dayouttemphilo.png',
                                              'dayouthum.png',
                                              'daywind.png')]
    return weather_data_json(F_to_C(temp_F), humidity, mi_to_km(wind_mph))

def get_next_bus_info(stopid):
    res = requests.get(NEXTBUS_URL,
                     params=dict(command='predictions',
                                 a='charles-river',
                                 stopId=stopid),
                     timeout=TIMEOUT
                    )
    if res.ok:
        for p in res.json()['predictions']:
            if p.get('direction'):
                title = '{}, {}:'.format(p['routeTitle'], p['direction']['title'])
                arrivals = ', '.join([bus['minutes']
                                      for bus in p['direction']['prediction']])\
                           + ' mins'
                return json.dumps(dict(title=title, arrivals=arrivals))
    return json.dumps(dict(title='(No Service)', arrivals='N.A.'))

def weather_data_json(temp=0, rel_humidity=0, wind_speed=0):
    return json.dumps(dict(temp    = '{:.1f}&deg;C'.format(temp),
                           humidity= '{:.0f}%'.format(rel_humidity),
                           wind    = '{:.0f} km/h'.format(wind_speed)))

def F_to_C(f):
    return (f-32)*5/9

def mi_to_km(mi):
    return mi * 1.609344
