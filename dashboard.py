import time
import argparse
import requests
import json

from flask import Flask, render_template, request
from werkzeug.serving import BaseRequestHandler
from utils import GBFSStationClient, get_blooimage_src

BLUEBIKE_GBFS = 'https://gbfs.bluebikes.com/gbfs/gbfs.json'
METEOBLUE_URL = 'https://www.meteoblue.com/en/weather/forecast/multimodel/cambridge_united-states-of-america_4931972'

app = Flask(__name__)

@app.route('/')
def main_page():
    return render_template("index.html")

@app.route('/get_meteoblue')
def get_meteoblue():
    try:
        return get_blooimage_src(METEOBLUE_URL)
    except:
        # TODO: add error image
        return '/static/img/favicon-32x32.png'

@app.route('/get_bluebikes')
def get_bluebikes():
    client = GBFSStationClient(BLUEBIKE_GBFS)
    stations = client.get_stations()
    requested = request.args.get('station_ids').split(',')
    return json.dumps({i: stations[i] for i in requested})

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
