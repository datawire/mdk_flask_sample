import sys

import logging

from flask import Flask, g
from mdk.flask import mdk_setup, MDKLoggingHandler

# Initialize Python logging first. We need to set the name of the logger,
# so logging.basicConfig won't cut it.

logger = logging.getLogger("monolith")
logger.setLevel(logging.INFO)                           # Log INFO and higher
logger.addHandler(logging.StreamHandler(sys.stdout))    # Always log to stdout

class CustomHandler(logging.StreamHandler):
    """Hand log messages to an MDK Session and then to another logging system."""

    def __init__(self, mdk):
        """
        :param mdk: A ``mdk.MDK`` instance.
        """
        logging.StreamHandler.__init__(self)
        self._wrapped_handler = MDKLoggingHandler(mdk)

    def emit(self, record):
        # log to MDK:
        logged_as = self._wrapped_handler.emit(record)
        # you can now use the result in your own logging, e.g. output to stdout:
        formatted = self.format(record)
        print("LOGGED %s - %s: %s" % (logged_as.traceId, logged_as.causalLevel,
                                      formatted))
                                      
# ...then get a Flask app going...
app = Flask(__name__)

# ...with two routes. This is all basic Flask stuff.
@app.route("/")
@app.route("/<path>")
def monolith(path="Pathless"):
    # This is a Python log that'll be vectored both to stdout (by the root
    # logger) and to MDK logging (by the handler installed by mdk_setup)
    logger.info("got a request for: %s" % path)

    return ("Got path %s" % path, 200)

@app.route("/new/<thing>")
def new_service(thing):
    # Use a sublogger here, to switch to a new category. Since this is a
    # child of the "monolith" logger, it inherits its configuration...
    logger = logging.getLogger("monolith.new-thing")

    # ...so this should still log to both places at once.
    logger.debug("switching to new-thing")
    logger.info("got a request for a new: %s" % thing)

    return ("New thing %s" % path, 200)

if __name__ == "__main__":
    # OK. Fire up the MDK...
    mdk = mdk_setup(app)

    # ...and link the MDK's logging into Python logging.
    # handler = MDKLoggingHandler(mdk)
    handler = CustomHandler(mdk) 
    logger.addHandler(handler)

    # Finally, start the server running.
    logger.info("And we're off!!!")
    app.run(port=7070)
