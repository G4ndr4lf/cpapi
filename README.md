# cpapi
General tool for interacting with Check Point Software MGMT Web API.

#### Configuration
* git clone https://github.com/themadhatterz/cpapi
* pip install -r requirements.txt
* Run via:
	* Local development server:
		* python(3) ~/cpapi/cpapiweb/run.py
	* Flask Web Server Deployments
		* http://flask.pocoo.org/docs/0.12/deploying/
* Configure Log Directories under /cpapiweb/app/\_\_init\_\_.py

#### Features
* Send custom commands based on reference guide.
* Add objects.
* Import objects from csv.
* Display policy in HTML.
* Run commands/scripts against devices.
