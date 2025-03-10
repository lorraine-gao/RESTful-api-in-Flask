#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
COMP9321 24T1 Assignment 2
Data publication as a RESTful service API

Getting Started
---------------

1. You MUST rename this file according to your zID, e.g., z1234567.py.

2. To ensure your submission can be marked correctly, you're strongly encouraged
   to create a new virtual environment for this assignment.  Please see the
   instructions in the assignment 1 specification to create and activate a
   virtual environment.

3. Once you have activated your virtual environment, you need to install the
   following, required packages:

   pip install python-dotenv==1.0.1
   pip install google-generativeai==0.4.1

   You may also use any of the packages we've used in the weekly labs.
   The most likely ones you'll want to install are:

   pip install flask==3.0.2
   pip install flask_restx==1.3.0
   pip install requests==2.31.0

4. Create a file called `.env` in the same directory as this file.  This file
   will contain the Google API key you generatea in the next step.

5. Go to the following page, click on the link to "Get an API key", and follow
   the instructions to generate an API key:

   https://ai.google.dev/tutorials/python_quickstart

6. Add the following line to your `.env` file, replacing `your-api-key` with
   the API key you generated, and save the file:

   GOOGLE_API_KEY=your-api-key

7. You can now start implementing your solution. You are free to edit this file how you like, but keep it readable
   such that a marker can read and understand your code if necessary for partial marks.

Submission
----------

You need to submit this Python file and a `requirements.txt` file.

The `requirements.txt` file should list all the Python packages your code relies
on, and their versions.  You can generate this file by running the following
command while your virtual environment is active:

pip freeze > requirements.txt

You can submit the two files using the following command when connected to CSE,
and assuming the files are in the current directory (remember to replace `zid`
with your actual zID, i.e. the name of this file after renaming it):

give cs9321 assign2 zid.py requirements.txt

You can also submit through WebCMS3, using the tab at the top of the assignment
page.

"""

# You can import more modules from the standard library here if you need them
# (which you will, e.g. sqlite3).
import os
from pathlib import Path
from flask import Flask, request, send_file
from flask_restx import Api, Resource, reqparse, fields
import sqlite3
from datetime import datetime
import requests

# You can import more third-party packages here if you need them, provided
# that they've been used in the weekly labs, or specified in this assignment,
# and their versions match.
from dotenv import load_dotenv          # Needed to load the environment variables from the .env file
import google.generativeai as genai     # Needed to access the Generative AI API

studentid = Path(__file__).stem         # Will capture your zID from the filename.
db_file   = f"{studentid}.db"           # Use this variable when referencing the SQLite database file.
txt_file  = f"{studentid}.txt"          # Use this variable when referencing the txt file for Q7.


# Load the environment variables from the .env file
load_dotenv()

# Configure the API key
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

# Create a Gemini Pro model
gemini = genai.GenerativeModel('gemini-pro')


# create database
if not os.path.exists(db_file):
   conn = sqlite3.connect(db_file)
   cursor = conn.cursor()
   cursor.execute('''CREATE TABLE IF NOT EXISTS stops (
                     stop_id INTEGER PRIMARY KEY,
                     name TEXT,
                     latitude REAL,
                     longitude REAL,
                     last_updated TEXT,
                     next_departure TEXT,
                     _links TEXT)''')
    
   cursor.execute('''CREATE TABLE IF NOT EXISTS departures (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     stop_id INTEGER,
                     platform TEXT,
                     direction TEXT,
                     operator_name TEXT,
                     destination_id TEXT,
                     FOREIGN KEY (stop_id) REFERENCES stops (stop_id)
                  )''')
   conn.commit()
   conn.close()


# Flask init
app = Flask(__name__)
api = Api(app) 
# ns = api.namespace('API', description='A smart API for the Deutsche Bahn')


first_parser = reqparse.RequestParser()
first_parser.add_argument('query', type=str, required=True, help="Query string for searching stops")

@api.route('/stops')
class StopsResource(Resource):
    @api.expect(first_parser)
    @api.response(200, 'OK')
    @api.response(201, 'CREATED')
    @api.response(400, 'BAD REQUEST')
    @api.response(404, 'NOT FOUND')
    @api.response(503, 'SERVICE UNAVAILABLE')
    
    def put(self):
        # use parser
        args = first_parser.parse_args()
        query = args.get('query')
        
        if not query:
           return {"message": "Query string is required."}, 400
         
        # call Deutsche Bahn API
        base_url = 'https://v6.db.transport.rest/locations'
        params = {
            'query': query,
            'results': 5   # limit is 5
        }
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
        except requests.RequestException:
            return {"message": "Deutsche Bahn API is not available."}, 503

        stops_data = response.json()
        stops = [stop for stop in stops_data if stop['type'] == 'stop']
        stops.sort(key=lambda x: x['id'])  # sort stop-id
        if not stops:
            return {"message": "No stops found."}, 404
         
      
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        response_data = []
        status_code = 200  

        cursor.execute('BEGIN')
        
        for stop in stops:
            stop_id = stop['id']
            last_updated = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
            _links = f"http://{request.host}/stops/{stop_id}"
            
            # check if the stop-id is exist, to decide the status code is 200 or 201
            cursor.execute('SELECT stop_id FROM stops WHERE stop_id = ?', (stop_id,))
            existing_stop = cursor.fetchone()
            
            cursor.execute('''
                INSERT INTO stops (stop_id, name, latitude, longitude, last_updated, _links)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(stop_id) DO UPDATE SET
                name=excluded.name, latitude=excluded.latitude, 
                longitude=excluded.longitude, last_updated=excluded.last_updated, 
                _links=excluded._links;
            ''', (stop_id, stop['name'], stop['location']['latitude'], stop['location']['longitude'], last_updated, _links))  
            
            # insert
            if not existing_stop:
               status_code = 201
            else:
               # update
               status_code = 200
            
            response_data.append({
                "stop_id": stop_id,
                "last_updated": last_updated,
                "_links": {"self": {"href": _links}}
            })

        conn.commit()
        conn.close()
        
        return response_data, status_code

# defalut duration is 120
def get_and_store_next_departure(cursor, stop_id, duration=120):
   base_url = f'https://v6.db.transport.rest/stops/{stop_id}/departures'
   params = {'duration': duration}  
   response = requests.get(base_url, params=params)
   
   if response.status_code == 200:
      departures_data = response.json()
      
      # first delete all record of this stop-id -----> to update 
      # cursor.execute('''
      #    DELETE FROM departures WHERE stop_id = ?
      # ''', (stop_id,))
        
      departures = departures_data.get('departures', [])
      for departure in departures:
         platform = departure.get('platform')
         direction = departure.get('direction')
         operator_name = departure.get('line', {}).get('operator', {}).get('name')
         destination_id = departure.get('destination', {}).get('id')

         if platform and direction:
            cursor.execute('''
               INSERT INTO departures (stop_id, platform, direction, operator_name, destination_id)
               VALUES (?, ?, ?, ?, ?)
            ''', (stop_id, platform, direction, operator_name, destination_id))
            
            last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # update last_updated field
            cursor.execute('''
               UPDATE stops
               SET last_updated = ?
               WHERE stop_id = ?
            ''', (last_updated, stop_id))
                  
      cursor.connection.commit()

      # response the original json
      return departures_data
   
   else:
      return False


sec_get_parser = reqparse.RequestParser()
sec_get_parser.add_argument('include', type=str, help='Separated by a comma')

stop_update_model = api.model('StopUpdate', {
   'name': fields.String(required=False, description='The new name of the stop'),
   'latitude': fields.Float(required=False, description='The new latitude of the stop'),
   'longitude': fields.Float(required=False, description='The new longitude of the stop'),
   'next_departure': fields.String(required=False, description='The new next departure information of the stop'),
   'last_updated': fields.String(required=False, description='The last updated time of the stop in yyyy-mm-dd-hh:mm:ss format',example="yyy-mm-dd-hh:mm:ss")
})

@api.route('/stops/<int:stop_id>')
class StopResource(Resource):
   @api.response(200, 'SUCCESS')
   @api.response(400, 'BAD REQUEST')
   @api.response(404, 'NOT FOUND')
   @api.response(503, 'SERVICE UNAVAILABLE')
    
   @api.expect(sec_get_parser)  
   def get(self, stop_id):
      args = sec_get_parser.parse_args()
      include_fields = args['include'].split(',') if args['include'] else []

      # check if it has forbidden fields in the include query 
      if 'stop_id' in include_fields or '_links' in include_fields:
         return {"message": "Including 'stop_id' or '_links' is not allowed."}, 400 
      
      conn = sqlite3.connect(db_file)
      conn.row_factory = sqlite3.Row
      cursor = conn.cursor()
        
      cursor.execute("SELECT * FROM stops WHERE stop_id = ?", (stop_id,))
      stop = cursor.fetchone()

      if not stop:
         conn.close()
         return {"message": f"The stop_id {stop_id} was not found in the database."}, 404
      
      departures_data = get_and_store_next_departure(cursor, stop_id)
      # find the first departure where the “platform” and “direction” field are both valid strings
      next_departure_info = None
      if departures_data:
         for departure in departures_data.get('departures', []):
            if 'platform' in departure and 'direction' in departure and departure['platform'] and departure['direction']:
               next_departure_info = f"Platform {departure['platform']} towards {departure['direction']}"
               
                # update next_departure field
               cursor.execute("""
                  UPDATE stops
                  SET next_departure = ?
                  WHERE stop_id = ?
               """, (departure['direction'], stop_id))
               cursor.connection.commit()
               break
               
      else:
         conn.close()
         return {"message": "Deutsche Bahn API is not available."}, 503 

      #if no valid info
      if not next_departure_info:
         conn.close()
         return {"message": "No valid departure information available"}, 404
            
      # get the info of this stop
      cursor.execute("SELECT * FROM stops WHERE stop_id = ?", (stop_id,))
      stop = cursor.fetchone()
      if not stop:
         conn.close()
         return {"message": f"Stop with ID {stop_id} not found"}, 404
      
      stop_data = {
         "stop_id": stop["stop_id"]
      }
        
      for field in ['last_updated', 'name', 'latitude', 'longitude']:
         if not include_fields or field in include_fields:
            stop_data[field] = stop[field]
      if not include_fields or 'next_departure' in include_fields:
         stop_data['next_departure'] = next_departure_info
         
      # links
      stop_data["_links"] = {"self": {"href": f"http://{request.host}/stops/{stop_id}"}}  
   
      cursor.execute("SELECT stop_id FROM stops WHERE stop_id > ? ORDER BY stop_id ASC LIMIT 1", (stop_id,))
      next_stop = cursor.fetchone()
      if next_stop:
         stop_data["_links"]["next"] = {
            "href": f"http://{request.host}/stops/{next_stop['stop_id']}"
         }
         
      cursor.execute("SELECT stop_id FROM stops WHERE stop_id < ? ORDER BY stop_id DESC LIMIT 1", (stop_id,))
      prev_stop = cursor.fetchone()
      if prev_stop:
         stop_data["_links"]["prev"] = {
            "href": f"http://{request.host}/stops/{prev_stop['stop_id']}"
         }
      conn.close()
      return stop_data, 200


   @api.response(200, 'OK')
   @api.response(400, 'BAD REQUEST')
   @api.response(404, 'NOT FOUND')
   def delete(self, stop_id):

      if stop_id == 0:
         return {"message": "The stop_id must be a positive integer."}, 400
   
      conn = sqlite3.connect(db_file)
      cursor = conn.cursor()

      cursor.execute("SELECT * FROM stops WHERE stop_id = ?", (stop_id,))
      stop = cursor.fetchone()

      if not stop:
         conn.close()
         return {"message": f"The stop_id {stop_id} was not found in the database."}, 404

      # if exists, delete
      cursor.execute("DELETE FROM stops WHERE stop_id = ?", (stop_id,))
      cursor.connection.commit()
      conn.close()

      return {
         "message": f"The stop_id {stop_id} was removed from the database.",
         "stop_id": stop_id
      }, 200


   @api.expect(stop_update_model)
   @api.response(200, 'OK')
   @api.response(400, 'Bad Request')
   @api.response(404, 'Stop not found')
   def patch(self, stop_id):
     
      data = request.json

      # check if the request body is none
      if not data:
         return {"message": "Request body can't be empty."}, 400
      
      known_fields = stop_update_model.keys()
      for field in data:
         if field not in known_fields:
            return {"message": f"Field '{field}' is not allowed."}, 400
               
      for field in ['name', 'next_departure']:
         if field in data and not data[field].strip():
            return {"message": f"{field} cannot be blank."}, 400

      # check latitude and longitude
      if 'latitude' in data and not -90 <= data['latitude'] <= 90:
         return {"message": "Latitude must be between -90 and 90."}, 400
      if 'longitude' in data and not -180 <= data['longitude'] <= 180:
         return {"message": "Longitude must be between -180 and 180."}, 400

      if 'last_updated' in data:
         try:
            datetime.strptime(data['last_updated'], '%Y-%m-%d-%H:%M:%S')
         except ValueError:
            return {"message": "Invalid last_updated format."}, 400
   
      last_updated = data.get('last_updated', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
      
      conn = sqlite3.connect(db_file)
      conn.row_factory = sqlite3.Row
      cursor = conn.cursor()

      # check if the stop-id is in the db
      cursor.execute("SELECT * FROM stops WHERE stop_id = ?", (stop_id,))
      stop = cursor.fetchone()

      if not stop:
         conn.close()
         return {"message": f"Stop with ID {stop_id} not found"}, 404
      
      update_statement = """
         UPDATE stops
         SET name = ?, 
               latitude = ?, 
               longitude = ?, 
               next_departure = ?, 
               last_updated = ?
         WHERE stop_id = ?
      """
      update_values = (
         data.get('name', stop['name']),
         data.get('latitude', stop['latitude']),
         data.get('longitude', stop['longitude']),
         data.get('next_departure', stop['next_departure']),  
         last_updated,
         stop_id,
      )
        
      cursor.execute(update_statement, update_values)
      cursor.connection.commit()
      conn.close()

      return {
         "stop_id": stop_id,
         "last_updated": last_updated,
         "_links": {
            "self": {
               "href": f"http://{request.host}/stops/{stop_id}"
            }
         }
      }, 200


def get_unique_operators(cursor, stop_id):
   cursor.execute('''
   SELECT DISTINCT operator_name FROM departures WHERE stop_id = ?
   ''', (stop_id,))
   return [row[0] for row in cursor.fetchall()]
 
 
@api.route('/operator-profiles/<int:stop_id>')
class OperatorProfiles(Resource):
   @api.response(200, 'Success')
   @api.response(400, 'Bad Request')
   @api.response(404, 'Not Found')
   @api.response(503, 'Service Unavailable')
   def get(self, stop_id):
      
      if stop_id == 0:
         return {"message": "The stop_id must be a positive integer."}, 400
      
      conn = sqlite3.connect(db_file)
      cursor = conn.cursor()
        
      cursor.execute("SELECT 1 FROM stops WHERE stop_id = ?", (stop_id,))
      if not cursor.fetchone():
         conn.close()
         return {"message": f"Stop ID {stop_id} not found in the database."}, 404
      
      #  notice the duration is 90
      if not get_and_store_next_departure(cursor, stop_id, 90):
         conn.close()
         return {"message": "Failed to retrieve German transportation system information."}, 503

      # get the unique operators
      operators = get_unique_operators(cursor, stop_id)

      profiles = []
      for operator in operators:
         try:
            question = f"Give me some substantial information about German transport operator {operator}, one paragraph is enough"
            response = gemini.generate_content(question)
            profile = {
               "operator_name": operator,
               "information": response.text
            }
            profiles.append(profile)
         except Exception as e:
            # if gemini isnt available
            conn.close()
            return {"message": str(e)}, 503
      
      response = {
         "stop_id": stop_id,
         "profiles": profiles
      }
      conn.close()
      return response


def valid_routes_exist(cursor):
   cursor.execute('''
      SELECT stop_id, destination_id FROM departures
   ''')
   valid_routes = [
      (row['stop_id'], row['destination_id']) for row in cursor.fetchall()
      if row['stop_id'] and row['destination_id']
   ]
   return any(
      cursor.execute('SELECT 1 FROM stops WHERE stop_id = ?', (stop,)).fetchone()
      and cursor.execute('SELECT 1 FROM stops WHERE stop_id = ?', (dest,)).fetchone()
      for stop, dest in valid_routes
   )

@api.route('/guide')
class TourismGuide(Resource):
    @api.response(200, 'Success')
    @api.response(400, 'Bad Request')
    @api.response(503, 'Service Unavailable')
    def get(self):
      conn = sqlite3.connect(db_file)
      conn.row_factory = sqlite3.Row
      cursor = conn.cursor()

      # loop departures table
      cursor.execute('''
         SELECT * FROM departures
      ''')
      departures = cursor.fetchall()

      # check if every stop_id and destination_id is exists in the stops table
      for departure in departures:
         cursor.execute('SELECT name FROM stops WHERE stop_id = ?', (departure['stop_id'],))
         source_stop = cursor.fetchone()
         cursor.execute('SELECT name FROM stops WHERE stop_id = ?', (departure['destination_id'],))
         destination_stop = cursor.fetchone()
         
         # if both of them exist
         if source_stop and destination_stop:
               source_name = source_stop['name']
               dest_name = destination_stop['name']

   
               question = f"Now I'm a tourist. I'd like to have a tourism guide. Tell me about substantial information about at least one point of interest at the {source_name} and at least one point of interest at the {dest_name}. Also tell me substantial information of tourist points of interest from {source_name} to {dest_name} in German and add other substantial information to enhence my experience when using the guide. Use english."
               response = gemini.generate_content(question)
               title = f"Tourism guide from {source_name} to {dest_name}.\n"
               if response.text:
                  txt_filename = txt_file  
                  with open(txt_filename, 'w') as file:
                     file.write(title)
                     file.write(response.text)
                  
                  return send_file(txt_filename, as_attachment=True, mimetype='text/plain')
               else:

                  return {}, 503

      # if check every record but there is no route
      conn.close()
      return {"message": "No valid public transport route found"}, 400


# @api.route('/test')
# class TestResource(Resource):
#     def get(self):
#         try:
#             base_url = 'https://v6.db.transport.rest/locations'
#             params = {'query': 'hbf', 'results': 5}
#             response = requests.get(base_url, params=params)
#             response.raise_for_status() 
#             data = response.json()
#             return data, 200
#         except requests.RequestException as e:
#             return {"error": str(e)}, 500
 
if __name__ == "__main__":
    app.run(port=5000)

