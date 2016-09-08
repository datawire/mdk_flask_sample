import logging

from flask import Flask, request

from mdk_flask import mdk_setup, mdk_category

# Initialize Python logging first...
logging.basicConfig(level=logging.INFO)

# ...then get a Flask app going...
app = Flask(__name__)

# ...then link MDK logging into it, using the default category "monolith" and
# the root logger as our base logger.
mdk_setup(app, "monolith")

# Simple Flask-route stuff.
@app.route("/")
@app.route("/<path>")
def monolith(path="Pathless"):
    # This is a Python log that'll be vectored both to stdout (by the root
    # logger) and to MDK logging (by the handler installed by mdk_setup)
    logging.info("got a request for: %s" % path)

    return ("Got path %s" % path, 200)

@app.route("/new/<thing>")
def new_service(thing):
    # Switch to using 'new-thing' as the MDK logging category..
    mdk_category("new-thing")

    # ...and, again, log to both places at once.
    logging.debug("switching to new-thing")
    logging.info("got a request for a new: %s" % thing)

    return ("New thing %s" % path, 200)

app.run()
