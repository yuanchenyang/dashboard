import time
import argparse
import requests
import json

from flask import Flask, render_template, request
from flask_caching import Cache
from werkzeug.serving import WSGIRequestHandler
from utils import GBFSStationClient, get_blooimage_src, scrape_wunderground,\
                  scrape_sailing_weather, get_next_bus_info, get_trash_info,\
                  get_bkb_routesetting

BaseRequestHandler = WSGIRequestHandler

config = dict(CACHE_TYPE="FileSystemCache",
              CACHE_DEFAULT_TIMEOUT=300,
              CACHE_THRESHOLD=10000,
              CACHE_DIR="./cache")

app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)

@app.route('/')
def main_page():
    return render_template("126_charles.html")

@app.route('/322')
def main_page_322():
    return render_template("322_western.html")

@app.route('/214')
def main_page_214():
    return render_template("214_brookline.html")


@app.route('/get_meteoblue')
@cache.cached(timeout=5*60)
def get_meteoblue():
    try:
        return get_blooimage_src(request.args.get('url', ''))
    except Exception as e:
        # TODO: add error image
        return '/static/img/favicon-32x32.png'

@app.route('/get_bluebikes')
@cache.cached(timeout=10)
def get_bluebikes():
    client = GBFSStationClient()
    stations = client.get_stations()
    requested = request.args.get('station_ids').split(',')
    return json.dumps({i: stations[i] for i in requested})

@app.route('/get_wunderground')
@cache.cached(timeout=30)
def get_wunderground():
    return scrape_wunderground(request.args.get('id'))

@app.route('/get_sailing_weather')
@cache.cached(timeout=30)
def get_sailing_weather():
    return scrape_sailing_weather()

@app.route('/get_nextbus')
@cache.cached(timeout=30)
def get_nextbus():
    return get_next_bus_info(request.args.get('stopid'))

@app.route('/get_trash')
@cache.cached(timeout=10*60)
def get_trash():
    return get_trash_info(request.args.get('placeid'),
                          request.args.get('clientid'))

@app.route('/get_bkb')
@cache.cached(timeout=10*60)
def get_bkb():
    return get_bkb_routesetting(request.args.get('cal_id'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
