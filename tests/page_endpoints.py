import json
from urllib.parse import urlencode, urlsplit

from bs4 import BeautifulSoup


def endpoints_from_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    endpoints = []

    endpoints.extend(card['url'] for card in
                     soup.select('[weather_station_card_id][url]'))
    endpoints.extend('/get_meteoblue?' + urlencode({'url': image['mb_url']})
                     for image in soup.select('img.meteoblue_img[mb_url]'))
    endpoints.extend(frame['src'] for frame in soup.select('iframe.mf[src]'))
    endpoints.extend('/get_weatherstory?' + urlencode({'wfo': card['nws_wfo']})
                     for card in soup.select('.nws_carousel[nws_wfo]'))
    endpoints.extend('/get_nextbus?' + urlencode({'stopid': card['nextbus_card_id']})
                     for card in soup.select('[nextbus_card_id]'))
    endpoints.extend('/get_trash?' + urlencode({'placeid': card['trash_card_id']})
                     for card in soup.select('[trash_card_id]'))
    endpoints.extend('/get_bkb?' + urlencode({'cal_id': card['bkb_card_id']})
                     for card in soup.select('[bkb_card_id]'))

    station_ids = [card['bluebike_card_id']
                   for card in soup.select('[bluebike_card_id]')]
    if station_ids:
        endpoints.append('/get_bluebikes?' + urlencode({
            'station_ids': ','.join(station_ids)
        }))

    soup.decompose()
    return sorted(set(endpoints))


def endpoint_paths(endpoints):
    return {urlsplit(endpoint).path for endpoint in endpoints}


def assert_endpoint_payload(endpoint, response):
    path = urlsplit(endpoint).path
    assert response.status_code == 200, (endpoint, response.status_code)
    body = response.get_data(as_text=True)
    assert body, endpoint

    if path in ('/get_pws', '/get_wunderground', '/get_sailing_weather'):
        weather = json.loads(body)
        assert set(weather) == {'temp', 'humidity', 'wind'}
        if path == '/get_pws':
            assert weather['temp'] != 'N/A', endpoint
            assert weather['humidity'] != 'N/A', endpoint
    elif path == '/get_meteoblue':
        assert body.startswith('//my.meteoblue.com/images/'), endpoint
    elif path == '/get_mf':
        assert 'forecast-table' in body, endpoint
    elif path == '/get_weatherstory':
        urls = json.loads(body)
        assert urls and all(url.startswith('http') for url in urls), endpoint
    elif path == '/get_bluebikes':
        stations = json.loads(body)
        assert stations, endpoint
        assert all('num_bikes_available' in station and
                   'num_docks_available' in station
                   for station in stations.values()), endpoint
    elif path == '/get_nextbus':
        assert set(json.loads(body)) == {'title', 'arrivals'}
    elif path == '/get_trash':
        assert set(json.loads(body)) == {'title', 'datestr', 'items'}
    elif path == '/get_bkb':
        assert set(json.loads(body)) == {'datestr', 'items'}
    else:
        raise AssertionError('No payload assertion for {}'.format(path))
