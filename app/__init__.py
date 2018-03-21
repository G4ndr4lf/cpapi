import os
import platform
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask

OSTYPE = platform.system()

if OSTYPE == 'Windows':
    BASEDIR = '{}\\'.format(os.getcwd())
if OSTYPE == 'Linux':
    BASEDIR = '/var/log/cpapi/'

app = Flask(__name__)
app.config['version'] = '2.0.0'
app.config['BASEDIR'] = BASEDIR

formatter = logging.Formatter('%(asctime)s %(levelname)s - '
                              '%(filename)s:%(funcName)s:%(lineno)d - '
                              '%(message)s')
handler = RotatingFileHandler(
    '{}cpapi.log'.format(app.config['BASEDIR']),
    maxBytes=10000000,
    backupCount=10)
handler.setFormatter(formatter)
if 'CPAPI' in os.environ:
    if os.environ['CPAPI'] == 'DEBUG':
        app.logger.setLevel('DEBUG')
else:
    app.logger.setLevel('INFO')
app.logger.addHandler(handler)
app.secret_key = os.urandom(25)

from app import views
