import atexit, mdk, requests, traceback, logging

from flask import request, request_started, got_request_exception, request_tearing_down

# Python logging handler that vectors logs off to MDK.
class MDKLogHandler(logging.StreamHandler):
    def __init__(self, app, log_level):
        # Initialize the superclass...
        super(MDKLogHandler, self).__init__()

        # ...then save the stuff we need to reference later. We need the app so
        # that we can use the app context later; we need the log level so we know
        # what we should log. (The level can be changed later -- just assign to it.)
        self.app = app
        self.log_level = self._fix_level(logging.getLevelName(log_level))

    def _fix_level(self, level):
        if level == 'WARNING':
            return 'WARN'
        else:
            return level

    # Emit a log record.
    def emit(self, record):
        # Switch into app context so that we can see e.g. global per-thread state...
        with self.app.app_context():
            # ...then grab the level of this record...
            level = self._fix_level(record.levelname)

            # Start by grabbing the default MDK session and category from the app...
            ssn = self.app.mdk_default_session
            category = self.app.mdk_default_category

            # ...but if we have a request, use the finer-grained stuff in the request
            # instead.

            if request:
                ssn = request.mdk_ssn
                category = request.mdk_category

            # Once that's done, make sure the session log level matches what we're asking for...
            ssn.trace(self.log_level)

            # ...and off we go.
            # 
            # WARNING: DO NOT CALL e.g. ssn.info() here -- it calls back into the Python logging
            # system. Oops. [ :) ] Use ssn._log() instead.
            ssn._log(level, category, self.format(record))

def on_request_started(sender, **extra):
    # Create a new MDK session at request start.
    request.mdk_ssn = sender.mdk.join(request.headers.get(sender.mdk.CONTEXT_HEADER))
    request.mdk_category = sender.mdk_default_category

def on_request_exception(sender, **extra):
    exc = extra.get("exception", None)
    request.mdk_ssn.fail_interaction(traceback.format_exc(exc))

def on_request_tearing_down(sender, **extra):
    request.mdk_ssn.finish_interaction()

def mdk_setup(app, category=None, logger=None):
    app.mdk = mdk.start()
    atexit.register(app.mdk.stop)
    request_started.connect(on_request_started, app)
    got_request_exception.connect(on_request_exception, app)
    request_tearing_down.connect(on_request_tearing_down, app)

    if category:
        mdk_logger(app, category, logger=logger)

def mdk_logger(app, default_category, logger=None):
    if not logger:
        logger = logging.getLogger()

    app.mdk_default_category = default_category
    app.mdk_default_session = app.mdk.session()

    logger.addHandler(MDKLogHandler(app, logger.level))

def mdk_category(category):
    request.mdk_category = category
