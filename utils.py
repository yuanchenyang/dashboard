import re
import json
import time
import requests
import icalendar
from datetime import datetime, date
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup, SoupStrainer
from gbfs.client import GBFSClient

BLUEBIKE_GBFS = 'https://gbfs.bluebikes.com/gbfs/gbfs.json'
WUNDERGROUND_URL = 'https://www.wunderground.com/weather'
METEOBLUE_URL = 'https://www.meteoblue.com/en/weather/forecast/meteogramone/'
SAILING_WEATHER_URL = 'http://sailing.mit.edu/weather/'
NEXTBUS_URL = 'https://retro.umoiq.com/service/publicJSONFeed'#'https://webservices.nextbus.com/service/publicJSONFeed'
TRASH_URL = 'https://recollect.a.ssl.fastly.net/api/places/{}/services/761/events.en-US.ics'
BKB_CAL_URL = 'https://widgets.mindbodyonline.com/widgets/schedules/{}/load_markup?options%5Bstart_date%5D={}'
MF_URL = 'https://www.mountain-forecast.com/peaks/{}'
MF_BASE = 'https://www.mountain-forecast.com'
NWS_WXSTORY_XML = 'https://www.weather.gov/source/{}/WxStory/WeatherStory.xml'
NWS_WXSTORY_DEFAULT = 'https://www.weather.gov/images/{}/WxStory/WeatherStory1.png'
TIMEOUT = 10
METEOBLUE_TIMEOUT = 10
PARSER = 'html.parser'
WUNDERGROUND_PARSER = 'lxml'
WUNDERGROUND_VALUE_CLASSES = ('current-temp', 'wu-unit-humidity', 'wu-unit-speed')

def _wu_value_class(css_class):
    # SoupStrainer matches against the whole class attribute string at parse
    # time, so a plain tuple only matches single-class elements. Wunderground now
    # wraps the humidity/wind values in multi-class spans (e.g. "test-false
    # wu-unit wu-unit-humidity"), so match on individual class tokens instead.
    return css_class is not None and bool(set(css_class.split()) & set(WUNDERGROUND_VALUE_CLASSES))

WUNDERGROUND_PARSE_ONLY = SoupStrainer(class_=_wu_value_class)

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
        soup = BeautifulSoup(res.text, PARSER)
    img_url = str(soup.find('div', id='blooimage')['data-href'])
    soup.decompose()
    return img_url

def scrape_wunderground(station_id):
    url = '{}/{}'.format(WUNDERGROUND_URL, station_id)
    with requests.get(url, timeout=TIMEOUT) as res:
        soup = BeautifulSoup(res.text, WUNDERGROUND_PARSER,
                             parse_only=WUNDERGROUND_PARSE_ONLY)
    def get_wu_text(class_id):
        try:
            return str(soup.find(class_=class_id).find("span", attrs={'class': 'wu-value'}).text)
        except Exception as e:
            print(e)
            return None
    temp_F, humidity, wind_mph = [get_wu_text(id) for id in
                                  WUNDERGROUND_VALUE_CLASSES]
    soup.decompose()
    return weather_data_json(F_to_C(temp_F), humidity, mi_to_km(wind_mph))

def scrape_sailing_weather():
    with requests.get(SAILING_WEATHER_URL, timeout=TIMEOUT) as res:
        soup = BeautifulSoup(res.text, PARSER)
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
        soup = BeautifulSoup(json.loads(res.text)['class_sessions'], PARSER)
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

def get_nws_weatherstory(wfo):
    """Image URLs of the weather stories the NWS office's front page is showing.

    The front page reads /source/<wfo>/WxStory/WeatherStory.xml and cycles
    through the graphicast(s) whose StartTime..EndTime window contains the
    current time (with radar disabled). The active graphics rotate between
    WeatherStory1.png, WeatherStory2.png, ... so a hardcoded filename goes stale
    as soon as a different story takes over; this always resolves to the live
    set, ordered by 'order' to match the page's slideshow. Falls back to the
    default image on any error or when nothing is active.
    """
    try:
        with requests.get(NWS_WXSTORY_XML.format(wfo), headers=HEADERS, timeout=TIMEOUT) as res:
            root = ET.fromstring(res.content)
    except Exception as e:
        print(e)
        return [NWS_WXSTORY_DEFAULT.format(wfo)]
    now = time.time()
    active = []
    for g in root.iter('graphicast'):
        def field(tag):
            el = g.find(tag)
            return el.text.strip() if el is not None and el.text else ''
        img = field('FullImage') or field('SmallImage')
        try:
            start, end = float(field('StartTime')), float(field('EndTime'))
        except ValueError:
            continue
        if img and field('radar') == '0' and start < now < end:
            order = field('order')
            active.append((int(order) if order.isdigit() else 999, img))
    if active:
        return [img for _, img in sorted(active)]
    return [NWS_WXSTORY_DEFAULT.format(wfo)]

def get_mf_table(url):
    with requests.get(MF_URL.format(url), headers=HEADERS) as res:
        soup = BeautifulSoup(res.text, PARSER)
    head = soup.find('head')
    # mountain-forecast content-hashes its CSS/JS filenames and re-hashes them on
    # every deploy, so hardcoded asset URLs eventually 404 and the panel renders
    # unstyled. Pull the current stylesheets, JS bundles and per-peak config
    # (FCGON/FCLOCATIONS drive the freezing-level graph) straight from the page.
    styles = ''.join(str(l) for l in head.find_all('link', rel='stylesheet')
                     if l.get('media') != 'print')
    config = ''.join(str(s) for s in head.find_all('script', src=False)
                     if s.string and any(k in s.string for k in
                                         ('FCLAYOUT', 'FCLOCATIONS', 'height_units')))
    scripts = ''.join(str(s) for s in soup.find_all('script', src=True)
                      if '/packs/js/' in s.get('src', '')
                      or '/assets/application' in s.get('src', ''))
    config += ''.join(str(s) for s in soup.find_all('script', src=False)
                      if s.string and 'FCGON' in s.string)
    table = str(soup.find('div', class_='forecast-table'))
    soup.decompose()
    def absolutize(html):
        return html.replace('href="/', 'href="{}/'.format(MF_BASE))\
                   .replace('src="/', 'src="{}/'.format(MF_BASE))
    return dict(mf_styles=absolutize(styles),
                mf_config=config,
                mf_scripts=absolutize(scripts),
                forecast_html=absolutize(table))

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
