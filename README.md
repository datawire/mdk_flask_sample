mdk_flask_sample
----------------

This is a really simple example of how to easily use MDK logging with a Flask app.

To use it, you'll need a Datawire account and its token:

- go to Datawire Mission Control at https://app.datawire.io
- sign up for a Datawire account
- get your Datawire Token using the "Copy Token" button in the left sidebar
- set DATAWIRE_TOKEN in your environment

To run the example, you'll probably want to use a virtualenv. After setting that up:

- pip install datawire_mdk flask blinker
- python monolith.py

and stand back! Logs from the monolith should appear in the Logs tag of Mission Control.
