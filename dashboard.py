import time
import argparse
import requests
import json

from collections import namedtuple
from flask import Flask, render_template, request, make_response, url_for
from flask_caching import Cache
from werkzeug.serving import WSGIRequestHandler

from utils import GBFSStationClient, get_blooimage_src, get_pws_observation,\
                  scrape_sailing_weather, get_next_bus_info, get_trash_info,\
                  get_bkb_routesetting, get_mf_table, get_nws_weatherstory,\
                  weather_data_json

BaseRequestHandler = WSGIRequestHandler

config = dict(CACHE_TYPE='FileSystemCache',
              CACHE_DEFAULT_TIMEOUT=300,
              CACHE_THRESHOLD=10000,
              CACHE_DIR='./cache')

app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)

Page = namedtuple('Page', ['name', 'id', 'template_name'])

available_pages = [Page('Cambridge + New Haven', 'cam_nh', 'cambridge_new_haven.html'),
                   Page('126 Charles St', 'charles126', '126_charles.html'),
                   Page('322 Western Ave', 'western322', '322_western.html'),
                   Page('214 Brookline St', 'brookline214', '214_brookline.html'),
                   Page('Northeast Climbing', 'ne-climbing', 'ne_climbing.html'),
                   ]

def get_page(page_id):
    for page in available_pages:
        if page.id == page_id:
            return page
    return available_pages[0]

def default_page_id():
    available_pages[0].id

def log_upstream_error(endpoint, error):
    app.logger.warning('%s failed: %s', endpoint, error)

@app.route('/')
def main_page():
    page_id = request.args.get('page_id',      # First choice
              request.cookies.get('page_id',   # Second choice
              default_page_id()))              # Fallback
    page = get_page(page_id)
    all_pages = available_pages
    return render_template('index.html', **locals())

@app.route('/set_page', methods=['POST'])
def set_page():
    print(request.form.get('page_id'))
    res = make_response("")
    res.set_cookie("page_id",
                   request.form.get('page_id', default_page_id()),
                   samesite='Strict')
    return res

@app.route('/get_mf')
@cache.cached(timeout=10*60, query_string=True)
def get_mf():
    try:
        data = get_mf_table(request.args.get('url', ''))
    except Exception as e:
        log_upstream_error('mountain-forecast', e)
        data = dict(mf_styles='', mf_config='', mf_scripts='', forecast_html='')
    return render_template('mf.html', **data)

@app.route('/get_weatherstory')
@cache.cached(timeout=10*60, query_string=True)
def get_weatherstory():
    return json.dumps(get_nws_weatherstory(request.args.get('wfo', '')))

@app.route('/get_meteoblue')
@cache.cached(timeout=15*60, query_string=True)
def get_meteoblue():
    try:
        return get_blooimage_src(request.args.get('url', ''))
    except Exception as e:
        log_upstream_error('meteoblue', e)
        return '/static/img/favicon-32x32.png'

@app.route('/get_bluebikes')
@cache.cached(timeout=10, query_string=True)
def get_bluebikes():
    requested = request.args.get('station_ids', '').split(',')
    try:
        client = GBFSStationClient()
        stations = client.get_stations()
        return json.dumps({i: stations[i] for i in requested})
    except Exception as e:
        log_upstream_error('Bluebikes', e)
        unavailable = dict(num_bikes_available='N.A.', num_docks_available='N.A.')
        return json.dumps({i: unavailable for i in requested})

@app.route('/get_wunderground')
@app.route('/get_pws')
@cache.cached(timeout=5*60, query_string=True)
def get_pws():
    try:
        return get_pws_observation(request.args.get('id'))
    except Exception as e:
        log_upstream_error('PWS observation', e)
        return weather_data_json(None, None, None)

@app.route('/get_sailing_weather')
@cache.cached(timeout=30, query_string=True)
def get_sailing_weather():
    try:
        return scrape_sailing_weather()
    except Exception as e:
        log_upstream_error('sailing weather', e)
        return weather_data_json(None, None, None)

@app.route('/get_nextbus')
@cache.cached(timeout=30, query_string=True)
def get_nextbus():
    try:
        return get_next_bus_info(request.args.get('stopid'))
    except Exception as e:
        log_upstream_error('NextBus', e)
        return json.dumps(dict(title='(No Service)', arrivals='N.A.'))

@app.route('/get_trash')
@cache.cached(timeout=10*60, query_string=True)
def get_trash():
    try:
        return get_trash_info(request.args.get('placeid'))
    except Exception as e:
        log_upstream_error('trash calendar', e)
        return json.dumps(dict(title='N.A.', datestr='N.A.', items='N.A.'))

@app.route('/get_bkb')
@cache.cached(timeout=10*60, query_string=True)
def get_bkb():
    try:
        return get_bkb_routesetting(request.args.get('cal_id'))
    except Exception as e:
        log_upstream_error('BKB calendar', e)
        return json.dumps(dict(datestr='N.A.', items='N.A.'))

@app.errorhandler(404)
def page_not_found(e):
    page = get_page(request.cookies.get('page_id'))
    all_pages = available_pages
    return render_template('404.html', **locals()), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
