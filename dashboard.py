import time
import argparse
import requests
import json

from flask import Flask, render_template, request
from werkzeug.serving import WSGIRequestHandler
from utils import GBFSStationClient, get_blooimage_src, scrape_wunderground,\
                  scrape_sailing_weather, get_next_bus_info, get_trash_info,\
                  get_bkb_routesetting

BaseRequestHandler = WSGIRequestHandler

app = Flask(__name__)

@app.route('/')
def main_page():
    return render_template("index.html")

@app.route('/get_meteoblue')
def get_meteoblue():
    try:
        return get_blooimage_src(request.args.get('url', ''))
    except Exception as e:
        # TODO: add error image
        return '/static/img/favicon-32x32.png'

@app.route('/get_bluebikes')
def get_bluebikes():
    client = GBFSStationClient()
    stations = client.get_stations()
    requested = request.args.get('station_ids').split(',')
    return json.dumps({i: stations[i] for i in requested})

@app.route('/get_wunderground')
def get_wunderground():
    return scrape_wunderground(request.args.get('id'))

@app.route('/get_sailing_weather')
def get_sailing_weather():
    return scrape_sailing_weather()

@app.route('/get_nextbus')
def get_nextbus():
    return get_next_bus_info(request.args.get('stopid'))

@app.route('/get_trash')
def get_trash():
    return get_trash_info(request.args.get('placeid'))

@app.route('/get_bkb')
def get_bkb():
    return get_bkb_routesetting(request.args.get('cal_id'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
