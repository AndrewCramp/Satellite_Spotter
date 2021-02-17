import json
import re
import os
from orbits import orbits
import pickle
import math
import mapbox
import numpy as np
import datetime as dt
import julian as j
from flask import Flask, render_template,request,jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from timezonefinder import TimezoneFinder
import pytz
import csv
tf = TimezoneFinder()
geocoder = mapbox.Geocoder(access_token = os.getenv("MAP_BOX_KEY"))


def getCityCoordinates():
    coordinates = np.array([0.0,0.0])
    location = geocoder.forward('Welland,ON', limit = 1)
    location = location.json()
    coordinates[0] = location['features'][0]['center'][1]
    coordinates[1] = location['features'][0]['center'][0]
    return coordinates

def get_satellite_tle(satellite_number):
    tle = None
    satellite = Satellite.query.filter_by(norad_number=satellite_number).first()
    current_time = dt.datetime.now()
    print(current_time - Satellite.retrival_time)
    if  satellite.retrival_time == None:
        tle = orbits.getTLE(satellite_number)
        satellite.tle = pickle.dumps(tle)
        satellite.retrival_time = dt.datetime.now()
        db.session.commit()
        print('retrival')
        return tle
    else:
        time_diff = current_time - satellite.retrival_time
        if time_diff.days > 1:
            tle = orbits.getTLE(satellite_number)
            satellite.tle = pickle.dumps(tle)
            satellite.retrival_time = dt.datetime.now()
            db.session.commit()
            print('retrival')
            return tle
        else:
            print('database')
            print(satellite.tle)
            return pickle.loads(satellite.tle)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
db = SQLAlchemy(app)
CORS(app, support_credentials=True)
@app.route("/", methods = ["GET","POST"])
def home():
    sat_list = Satellite.query.all()
    satellite_dict = dict()
    incorrect_value_flag = False
    for satellite in sat_list:
        satellite_dict[satellite.name] = satellite.norad_number
    
    time_diff = 0
    current_time = j.to_jd(dt.datetime.now(orbits.utc), fmt='jd')
    
    if 'satellite' in session:
        time_diff = (current_time - session['retrival_time'])
    retrival_time_local = dt.datetime.now(orbits.utc)
    if time_diff > 0.0694 and 'satellite' in session:
        session['retrival_time'] = j.to_jd(dt.datetime.now(orbits.utc), fmt='jd')
        while True:
             try:
                 timezone_str = tf.timezone_at(lng = session['user_coord'][1],lat = session['user_coord'][0])
                 timezone = pytz.timezone(timezone_str)
             except:
                 print("invalid timezone")
                 session['user_coord'][0] = session['user_coord'][0] + 1
                 continue
             break
        retrival_time_local= dt.datetime.now(timezone)
    
    if session.get('satellite') == None:
        session['user_coord'] = [40.0,0.0]
        session['satellite_coord'] = [0.0,0.0]
        session['satellite_name'] = "Hubble Space Telescope"
        session['satellite'] = satellite_dict[session['satellite_name']]
        session['tle'] = get_satellite_tle(session['satellite'])
        while True:
             try:
                 timezone_str = tf.timezone_at(lng = session['user_coord'][1],lat = session['user_coord'][0])
                 timezone = pytz.timezone(timezone_str)
             except:
                 print("invalid timezone")
                 session['user_coord'][0] = session['user_coord'][0] + 1
                 continue
             break
        session['retrival_time'] = j.to_jd(dt.datetime.now(orbits.utc), fmt='jd')
        retrival_time_local= dt.datetime.now(timezone)
    
    if request.method == "POST":
        new_coords = [float(request.form["latitude"]), float(request.form["longitude"])]
        satellite_re = '^[0-9]{5}$'
        print(repr(request.form["satellite_id"]))
        match = re.match(satellite_re,request.form["satellite_id"])
        if match:
            print("id")
            try:
                new_id = request.form["satellite_id"]
            except:
                new_id = session['satellite']
                incorrect_valuee_flag = True
        else:
            print("name")
            try:
                new_id = satellite_dict[request.form["satellite_id"]]
            except:
                new_id = session['satellite']
                incorrect_valuee_flag = True
        if new_id != session['satellite']  or new_coords != session['user_coord']:
            session['user_coord'] = new_coords
            while True:
                try:
                    timezone_str = tf.timezone_at(lng = session['user_coord'][1],lat = session['user_coord'][0])
                    timezone = pytz.timezone(timezone_str)
                except:
                    print("invalid timezone")
                    session['user_coord'][0] = session['user_coord'][0] + 1
                    continue
                break
            tle = get_satellite_tle(new_id)
            session['tle'] = tle
            session['retrival_time'] = j.to_jd(dt.datetime.now(orbits.utc), fmt='jd')
            session['satellite'] = new_id
            session['satellite_name'] = request.form["satellite_id"]
            retrival_time_local= dt.datetime.now(timezone)
    orbit_propogation = orbits.propogate_orbit(session['tle'], session['user_coord'])
    temp_coords = []
    for coord_array in orbit_propogation:
        temp_coords.extend(coord_array)
    
    sat_passes = orbits.check_passes(temp_coords, session['user_coord'], orbits.getSemiMajorAxis(session['tle']['mean motion']), retrival_time_local)
    startTime = sat_passes['start time']
    startAzimuth = sat_passes['start azimuth']
    endTime = sat_passes['end time']
    endAzimuth = sat_passes['end azimuth']
    date = sat_passes['date']
    passes = sat_passes['passes']
    session['satellite_coord'] = orbits.getFuturePosition(time_diff, session['tle'])
    session['look angle'] = orbits.lookAngle(session['user_coord'], session['satellite_coord'],orbits.getSemiMajorAxis(session['tle']['mean motion']))
    return render_template("index.html",passes = passes,startTime = startTime, date = date,startAzimuth = startAzimuth,
            endTime = endTime,endAzimuth = endAzimuth, elev = round(session['look angle'][0],2), 
            az = round(session['look angle'][1],2), lat = round(session['satellite_coord'][0],2),
            lon = round(session['satellite_coord'][1],2), sat_id = session['satellite'],
            latg = round(session['user_coord'][0],2), longg = round(session['user_coord'][1],2),
            coords = orbit_propogation, inclination = round(session['tle']['inclination']*180/math.pi,2),
            perigee = round(session['tle']['perigee']*180/math.pi,2), eccentricity = round(session['tle']['eccentricity'],5),
            satellite_dict = satellite_dict, sat_name = session['satellite_name'],  mapbox_key=os.getenv("MAP_BOX_KEY"), bad_value=incorrect_value_flag)
    


@app.route("/Update", methods = ["Get","POST"])
def update():
    lAngle = 0
    current_time = j.to_jd(dt.datetime.now(orbits.utc), fmt='jd')
    time_diff = (current_time - session['retrival_time'])
    if time_diff > 0.0694: 
        return redirect('/')
    session['satellite_coord'] = orbits.getFuturePosition(0, session['tle'])
    lAngle = orbits.lookAngle(session['user_coord'],session['satellite_coord'], orbits.getSemiMajorAxis(session['tle']['mean motion']))
    elevation = lAngle[0]
    azimuth = lAngle[1]
    return jsonify(elev = round(elevation,2), az = round(azimuth,2), lat = round(session['satellite_coord'][0],2), 
            lon = round(session['satellite_coord'][1],2), latg = round(session['user_coord'][0],2), 
            longg = round(session['user_coord'][1],2))

@app.route("/look_angle/<satellite>/<userlat>/<userlon>", methods = ["Get"])
def look_angle_prop(satellite, userlat, userlon):
    tle = orbits.get_satellite_tle(satellite)
    count = 0
    current_time = j.to_jd(dt.datetime.now(orbits.utc), fmt='jd')
    lookangles = {
            'time': [],
            'elevation':[],
            'azimuth':[],
            }
    observe_coord = [float(userlat), float(userlon)]
    coordinates = orbits.propogate_orbit(tle, observe_coord)
    for coord_array in coordinates:
            for coord in coord_array:
                ret = orbits.lookAngle(observe_coord, coord, orbits.getSemiMajorAxis(tle['mean motion']))
                lookangles['time'].append(count*8.33e-4)
                lookangles['elevation'].append(ret[0])
                lookangles['azimuth'].append(ret[1])
                count += 1
    return jsonify(lookangles = lookangles)
                


class Satellite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    norad_number = db.Column(db.Integer, unique=False, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    tle = db.Column(db.PickleType, nullable=True)
    retrival_time = db.Column(db.DateTime, nullable=True)

    
    def __repr__(self):
        data = self.name
        return f'<Satellite {data}>'


if (__name__ == "__main__"):
    os.getenv("MAP_BOX_KEY")
    app.run(host='localhost')
