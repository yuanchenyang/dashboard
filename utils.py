import re
import json
import requests
import icalendar
from datetime import datetime, date
from bs4 import BeautifulSoup
from gbfs.client import GBFSClient

BLUEBIKE_GBFS = 'https://gbfs.bluebikes.com/gbfs/gbfs.json'
WUNDERGROUND_URL = 'https://www.wunderground.com/weather'
METEOBLUE_URL = 'https://www.meteoblue.com/en/weather/forecast/meteogramone/'
SAILING_WEATHER_URL = 'http://sailing.mit.edu/weather/'
NEXTBUS_URL = 'https://retro.umoiq.com/service/publicJSONFeed'#'https://webservices.nextbus.com/service/publicJSONFeed'
TRASH_URL = 'https://recollect.a.ssl.fastly.net/api/places/{}/services/761/events.en-US.ics'
BKB_CAL_URL = 'https://widgets.mindbodyonline.com/widgets/schedules/{}/load_markup?options%5Bstart_date%5D={}'
MF_URL = 'https://www.mountain-forecast.com/peaks/{}'
TIMEOUT = 10
METEOBLUE_TIMEOUT = 10

class GBFSStationClient(GBFSClient):
    def __init__(self, language=None, json_fetcher=None):
        GBFSClient.__init__(self, BLUEBIKE_GBFS, language=language, json_fetcher=json_fetcher)
        station_information = self.request_feed('station_information')
        self.stations = {s['legacy_id']: s
                         for s in station_information['data']['stations']}

    def get_stations(self):
        for s in self.request_feed('station_status')['data']['stations']:
            if 'legacy_id' in s:
                self.stations[s['legacy_id']].update(s)
        return self.stations

# Use this otherwise webpage returns browser unsupported error
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
COOKIES = {'precip': 'MILLIMETER',
           'speed': 'KILOMETER_PER_HOUR',
           'temp': 'CELSIUS'}

def get_blooimage_src(url):
    with requests.get(METEOBLUE_URL + url, cookies=COOKIES, timeout=METEOBLUE_TIMEOUT) as res:
        soup = BeautifulSoup(res.text, 'lxml')
    img_url = str(soup.find('div', id='blooimage')['data-href'])
    soup.decompose()
    return img_url

def scrape_wunderground(station_id):
    url = '{}/{}'.format(WUNDERGROUND_URL, station_id)
    with requests.get(url, timeout=TIMEOUT) as res:
        soup = BeautifulSoup(res.text, "lxml")
    def get_wu_text(class_id):
        try:
            return str(soup.find(class_=class_id).find("span", attrs={'class': 'wu-value'}).text)
        except Exception as e:
            print(e)
            return None
    vals = soup.find_all("span", attrs={'class': 'wu-value'})
    temp_F, humidity, wind_mph = [get_wu_text(id) for id in
                                  ('current-temp', 'wu-unit-humidity', 'wu-unit-speed')]
    soup.decompose()
    return weather_data_json(F_to_C(temp_F), humidity, mi_to_km(wind_mph))

def scrape_sailing_weather():
    with requests.get(SAILING_WEATHER_URL, timeout=TIMEOUT) as res:
        soup = BeautifulSoup(res.text, "lxml")
    temp_F, humidity, wind_mph = [float(soup.find("a", attrs={'href': val}).text)
                                  for val in ('dayouttemphilo.png',
                                              'dayouthum.png',
                                              'daywind.png')]
    soup.decompose()
    return weather_data_json(F_to_C(temp_F), humidity, mi_to_km(wind_mph))

def get_next_bus_info(stopid):
    params = dict(command='predictions',
                  a='charles-river',
                  stopId=stopid)
    with requests.get(NEXTBUS_URL, params=params, timeout=TIMEOUT) as res:
        if res.ok:
            for p in res.json()['predictions']:
                if p.get('direction'):
                    title = '{}, {}:'.format(p['routeTitle'], p['direction']['title'])
                    arrivals = ', '.join([bus['minutes']
                                          for bus in p['direction']['prediction']])\
                               + ' mins'
                    return json.dumps(dict(title=title, arrivals=arrivals))
        return json.dumps(dict(title='(No Service)', arrivals='N.A.'))

def get_trash_info(placeid):
    title, datestr, items = 'N.A.', 'N.A.', 'N.A.'
    with requests.get(TRASH_URL.format(placeid), timeout=TIMEOUT) as res:
        if res.ok:
            cal = icalendar.Calendar.from_ical(res.text)
            title = str(cal['X-WR-CALNAME']).split(',')[0]
            today = date.today()
            for event in cal.subcomponents:
                dstr = str(event['DTSTART'].to_ical())
                event_date = datetime.strptime(dstr, "b'%Y%m%d'").date()
                if event_date >= today:
                    items = str(event['DESCRIPTION'])
                    datestr = event_date.strftime('%a %b %d')
                    break
        return json.dumps(dict(title=title, datestr=datestr, items=items))

def get_bkb_routesetting(cal_id):
    datestr, items = 'N.A.', 'N.A.'
    today = datetime.now().strftime('%F')
    with requests.get(BKB_CAL_URL.format(cal_id, today), timeout=TIMEOUT) as res:
        soup = BeautifulSoup(json.loads(res.text)['class_sessions'], "lxml")
    for day in soup.select('[class=bw-widget__day]'):
        dt_str = str(day.select('time[class=hc_starttime]')[0].attrs['datetime'])
        sessions = [format_session(str(s.text).strip())
                    for s in day.select('[class=bw-session__name]')
                    if 'Setting' in s.text]
        if len(sessions) > 0:
            datestr = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M').date().strftime('%a %b %d')
            items = ', '.join(sessions)
            break
    soup.decompose()
    return json.dumps(dict(datestr=datestr, items=items))

def get_mf_table(url):
    with requests.get(MF_URL.format(url), headers=HEADERS) as res:
        soup = BeautifulSoup(res.text, 'lxml')
    html_rel = str(soup.find('div', class_='forecast-table'))
    html_abs = html_rel.replace('src="/', 'src="https://www.mountain-forecast.com/')\
                       .replace('/images/mtn_fl_clear.jpg', 'https://www.mountain-forecast.com/images/mtn_fl_clear.jpg')
    soup.decompose()
    return html_abs

def format_session(session):
    return re.match('^Setting - (.*)$', session).groups()[0]

def weather_data_json(temp=0, rel_humidity=0, wind_speed=0):
    return json.dumps(dict(temp    = 'N/A' if temp is None else f'{temp:.1f}&deg;C',
                           humidity= 'N/A' if rel_humidity is None else f'{float(rel_humidity):.0f}%',
                           wind    = 'N/A' if wind_speed is None else f'{wind_speed:.0f} km/h'))

def F_to_C(f):
    if f is not None:
        return (float(f)-32)*5/9

def mi_to_km(mi):
    if mi is not None:
        return float(mi) * 1.609344
