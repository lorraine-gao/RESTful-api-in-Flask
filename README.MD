# RESTful-api-in-Flask

## background
 To practice RESTful api and learn flash frame, I build a new set of RESTful api based on German public transport system which provide features including importing the stop, retrieve the stop and ect. 
 
 FYI there is a new database to store data which retrieve from original endpoints.
 ### original api reference: https://v6.db.transport.rest/

 Besides re-build a new API  I used Gemini api creatively. Specifically, I set prompt in advance to generate answer. The prompt contains variables and goals. 
 
 a. The first one feature is that users can know detailed infomation abou each operator who is operating a service departing from a desired stop within 90 minutes.

 b. Second is that one GET method will return a TXT file to help a tourist explore points of interests around a journey using stops from database.

## how to use
  1. You could use virtual enviroment if you like. 

      To create: `python3 -m venv [path]`

      to Activate: `source bin/activate`
  2. Pls install these packages:

    pip install python-dotenv==1.0.1
    pip install google-generativeai==0.4.1
    pip install flask==3.0.2
    pip install flask_restx==1.3.0
    pip install requests==2.31.0

  3. Go to the following page, click on the link to "Get an API key", and follow the instructions to generate an API key:
  
      https://ai.google.dev/tutorials/python_quickstart

   4. Add the following line to your `.env` file, replacing `your-api-key` with the API key you generated, and save the file:

      `GOOGLE_API_KEY=your-api-key`

  5. use `python3 flask.py` to start and go to page http://127.0.0.1:5000 which automaticlly generate Swagger doc

## lessons learned

## limitations

