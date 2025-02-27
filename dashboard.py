import time
import argparse
import requests
import json

from collections import namedtuple
from flask import Flask, render_template, request, make_response, url_for
from flask_caching import Cache
from werkzeug.serving import WSGIRequestHandler

from utils import GBFSStationClient, get_blooimage_src, scrape_wunderground,\
                  scrape_sailing_weather, get_next_bus_info, get_trash_info,\
                  get_bkb_routesetting, get_mf_table

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
    forecast_html = get_mf_table(request.args.get('url', ''))
    return render_template('mf.html', forecast_html=forecast_html)

@app.route('/get_meteoblue')
@cache.cached(timeout=5*60, query_string=True)
def get_meteoblue():
    try:
        return get_blooimage_src(request.args.get('url', ''))
    except Exception as e:
        # TODO: add error image
        return '/static/img/favicon-32x32.png'

@app.route('/get_bluebikes')
@cache.cached(timeout=10, query_string=True)
def get_bluebikes():
    client = GBFSStationClient()
    stations = client.get_stations()
    requested = request.args.get('station_ids').split(',')
    return json.dumps({i: stations[i] for i in requested})

@app.route('/get_wunderground')
@cache.cached(timeout=30, query_string=True)
def get_wunderground():
    return scrape_wunderground(request.args.get('id'))

@app.route('/get_sailing_weather')
@cache.cached(timeout=30, query_string=True)
def get_sailing_weather():
    return scrape_sailing_weather()

@app.route('/get_nextbus')
@cache.cached(timeout=30, query_string=True)
def get_nextbus():
    return get_next_bus_info(request.args.get('stopid'))

@app.route('/get_trash')
@cache.cached(timeout=10*60, query_string=True)
def get_trash():
    return get_trash_info(request.args.get('placeid'))

@app.route('/get_bkb')
@cache.cached(timeout=10*60, query_string=True)
def get_bkb():
    return get_bkb_routesetting(request.args.get('cal_id'))

@app.errorhandler(404)
def page_not_found(e):
    page = get_page(request.cookies.get('page_id'))
    all_pages = available_pages
    return render_template('404.html', **locals()), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
