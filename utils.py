import re
import json
import os
import tempfile
import threading
import time
import requests
import icalendar
from datetime import datetime, date
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup, SoupStrainer
from gbfs.client import GBFSClient

BLUEBIKE_GBFS = 'https://gbfs.bluebikes.com/gbfs/gbfs.json'
PWS_OBSERVATIONS_URL = 'https://api.weather.com/v2/pws/observations/current'
WUNDERGROUND_PWS_URL = 'https://www.wunderground.com/dashboard/pws/{}'
METEOBLUE_URL = 'https://www.meteoblue.com/en/weather/forecast/meteogramone/'
SAILING_WEATHER_URL = 'http://sailing.mit.edu/weather/'
NEXTBUS_URL = 'https://retro.umoiq.com/service/publicJSONFeed'#'https://webservices.nextbus.com/service/publicJSONFeed'
TRASH_URL = 'https://recollect.a.ssl.fastly.net/api/places/{}/services/761/events.en-US.ics'
BKB_CAL_URL = 'https://widgets.mindbodyonline.com/widgets/schedules/{}/load_markup?options%5Bstart_date%5D={}'
MF_URL = 'https://www.mountain-forecast.com/peaks/{}'
MF_BASE = 'https://www.mountain-forecast.com'
NWS_WXSTORY_XML = 'https://www.weather.gov/source/{}/WxStory/WeatherStory.xml'
NWS_WXSTORY_DEFAULT = 'https://www.weather.gov/images/{}/WxStory/WeatherStory1.png'
TIMEOUT = (3.05, 10)
METEOBLUE_TIMEOUT = (3.05, 10)
PWS_PAGE_MAX_BYTES = 2 * 1024 * 1024
PWS_API_KEY_CACHE_FILE = os.environ.get(
    'WEATHER_API_KEY_CACHE_FILE',
    os.path.join(tempfile.gettempdir(), 'dashboard-weather-api-key'))
PWS_API_KEY_PATTERN = re.compile(
    rb'https://api\.weather\.com/v2/pws[^"\'<>\s]{0,2048}?'
    rb'apiKey=([A-Za-z0-9_-]{16,128})',
    re.IGNORECASE)
PWS_API_KEY_VALUE_PATTERN = re.compile(r'^[A-Za-z0-9_-]{16,128}$')
PWS_AUTH_FAILURE_STATUSES = {401, 403}
PARSER = 'html.parser'
METEOBLUE_PARSE_ONLY = SoupStrainer('div', id='blooimage')

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
WUNDERGROUND_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/126 Safari/537.36')
}
COOKIES = {'precip': 'MILLIMETER',
           'speed': 'KILOMETER_PER_HOUR',
           'temp': 'CELSIUS'}

_pws_api_key = None
_pws_api_key_lock = threading.Lock()

def get_blooimage_src(url):
    soup = None
    try:
        with requests.get(METEOBLUE_URL + url, cookies=COOKIES,
                          timeout=METEOBLUE_TIMEOUT) as res:
            res.raise_for_status()
            soup = BeautifulSoup(res.content, PARSER,
                                 parse_only=METEOBLUE_PARSE_ONLY)
        blooimage = soup.find('div', id='blooimage')
        if blooimage is None or not blooimage.get('data-href'):
            raise ValueError('Meteoblue response did not contain a blooimage URL')
        return str(blooimage['data-href'])
    finally:
        if soup is not None:
            soup.decompose()

def _read_cached_pws_api_key():
    try:
        with open(PWS_API_KEY_CACHE_FILE, encoding='ascii') as cache_file:
            api_key = cache_file.read(129).strip()
    except (OSError, UnicodeError):
        return None
    if PWS_API_KEY_VALUE_PATTERN.fullmatch(api_key):
        return api_key
    return None


def _store_pws_api_key(api_key):
    cache_dir = os.path.dirname(PWS_API_KEY_CACHE_FILE) or '.'
    os.makedirs(cache_dir, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix='.dashboard-weather-api-key-', dir=cache_dir, text=True)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='ascii') as cache_file:
            cache_file.write(api_key)
        os.replace(temporary_path, PWS_API_KEY_CACHE_FILE)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def _discover_pws_api_key(station_id):
    station_id = str(station_id or '').upper()
    if not re.fullmatch(r'[A-Z0-9]{2,32}', station_id):
        raise ValueError('Invalid PWS station ID')

    page = bytearray()
    with requests.get(WUNDERGROUND_PWS_URL.format(station_id),
                      headers=WUNDERGROUND_HEADERS, timeout=TIMEOUT,
                      stream=True) as res:
        res.raise_for_status()
        for chunk in res.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            page.extend(chunk)
            if len(page) > PWS_PAGE_MAX_BYTES:
                raise ValueError('Wunderground station page exceeded size limit')

    match = PWS_API_KEY_PATTERN.search(page)
    if match is None:
        raise ValueError('Wunderground station page did not contain a PWS API key')
    return match.group(1).decode('ascii')


def get_pws_api_key(station_id, stale_key=None):
    global _pws_api_key

    with _pws_api_key_lock:
        if _pws_api_key and (stale_key is None or _pws_api_key != stale_key):
            return _pws_api_key

        cached_key = _read_cached_pws_api_key()
        if cached_key and (stale_key is None or cached_key != stale_key):
            _pws_api_key = cached_key
            return cached_key

        api_key = _discover_pws_api_key(station_id)
        _store_pws_api_key(api_key)
        _pws_api_key = api_key
        return api_key


def _raise_for_pws_status(response):
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise requests.HTTPError(
            'PWS API returned HTTP {}'.format(response.status_code),
            response=response) from error


def get_pws_observation(station_id, api_key=None):
    configured_api_key = api_key or os.environ.get('WEATHER_API_KEY')
    current_api_key = configured_api_key or get_pws_api_key(station_id)

    for attempt in range(2):
        params = dict(stationId=station_id, format='json', units='m',
                      numericPrecision='decimal', apiKey=current_api_key)
        stale_key = False
        with requests.get(PWS_OBSERVATIONS_URL, params=params,
                          timeout=TIMEOUT) as res:
            if res.status_code in PWS_AUTH_FAILURE_STATUSES:
                if configured_api_key or attempt > 0:
                    _raise_for_pws_status(res)
                stale_key = True
            elif res.status_code == 204:
                return weather_data_json(None, None, None)
            else:
                _raise_for_pws_status(res)
                observations = res.json().get('observations', [])

        if stale_key:
            current_api_key = get_pws_api_key(
                station_id, stale_key=current_api_key)
            continue
        if not observations:
            return weather_data_json(None, None, None)
        observation = observations[0]
        metric = observation.get('metric', {})
        return weather_data_json(metric.get('temp'),
                                 observation.get('humidity'),
                                 metric.get('windSpeed'))

    raise RuntimeError('PWS authentication retry failed')

def scrape_sailing_weather():
    with requests.get(SAILING_WEATHER_URL, timeout=TIMEOUT) as res:
        res.raise_for_status()
        soup = BeautifulSoup(res.content, PARSER)
    try:
        temp_F, humidity, wind_mph = [float(soup.find("a", attrs={'href': val}).text)
                                      for val in ('dayouttemphilo.png',
                                                  'dayouthum.png',
                                                  'daywind.png')]
    finally:
        soup.decompose()
    return weather_data_json(F_to_C(temp_F), humidity, mi_to_km(wind_mph))

def get_next_bus_info(stopid):
    params = dict(command='predictions',
                  a='charles-river',
                  stopId=stopid)
    with requests.get(NEXTBUS_URL, params=params, timeout=TIMEOUT) as res:
        res.raise_for_status()
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
        res.raise_for_status()
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
        res.raise_for_status()
        soup = BeautifulSoup(res.json()['class_sessions'], PARSER)
    try:
        for day in soup.select('[class=bw-widget__day]'):
            dt_str = str(day.select('time[class=hc_starttime]')[0].attrs['datetime'])
            sessions = [format_session(str(s.text).strip())
                        for s in day.select('[class=bw-session__name]')
                        if 'Setting' in s.text]
            if len(sessions) > 0:
                datestr = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M').date().strftime('%a %b %d')
                items = ', '.join(sessions)
                break
    finally:
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
            res.raise_for_status()
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
    soup = None
    try:
        with requests.get(MF_URL.format(url), headers=HEADERS,
                          timeout=TIMEOUT) as res:
            res.raise_for_status()
            soup = BeautifulSoup(res.content, PARSER)
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
    finally:
        if soup is not None:
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
