# mdk_log_crunch.py is an example of some ways one might analyze MDK LogEvents to 
# learn some simple things about the paths calls take through one's service fabric.
#
# NB: this is using some low(ish)-level stuff in the MDK. 100% guaranteed that the
# APIs in use will change, possibly dramatically -- however, the LogEvent structure
# will probably not change much.
#
# At least, the structure as seen by the MDK probably won't change much. Here it is,
# using a horrible mishmash of Quark typing and Python block structuring:
#
# LogEvent event {
#   SharedContext context {
#     String traceId        # Unique ID of the trace containing this event
#     Map<String, Object> properties    # Shared properties
#     LamportClock clock {
#       List<int> clocks    # Lamport clock vector
#     }
#   }
#   long timestamp          # ms since the UNIX epoch
#   String node             # UUID of process logging this event
#   String level            # "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"
#   String category         # human-readable text identifying what logged this
#   String contentType      # Per MIME
#   String text             # Should really be "body" -- must conform to contentType
# }
#
# So event.context.clock.clocks (in Python) is the Lamport array, and event.timestamp is
# the timestamp.
#
# HOWEVER, for ElasticSearch, we flatten this object, using '-' between levels of hierarchy.
# So in the ElasticSearch document, context.clock.clocks becomes "context-clock-clocks", and
# if the properties map is { 'prop1': 47, 'prop2': 'hello' }, then the ElasticSearch document
# will contain "context-properties-prop1" and "context-properties-prop2".
#
# We do the flattening to cope with the fact that structured data is a pain to build searches
# for (especially with e.g. Kibana), and this code is designed partly to root around in
# the data structures in ways that would be possible with ElasticSearch. That means that even
# in cases where we could use LogEvent methods to deconstruct things, we'll do things by hand
# instead.

import sys

import datetime
import json
import signal
import threading
import time

# OK. Get logging going pretty early, since Quark will try to use it to report fatal errors 
# in Quark-generated code.
import logging

logging.basicConfig(level=logging.INFO)

# Once that's done, pull in the MDK stuff that we need.

import mdk
import mdk_runtime

# set_interval is a utility to set up repeating function calls. We use it for heartbeats, 
# and to periodically sweep the log table to output traces.
def set_interval(func, sec):
    def func_wrapper():
        set_interval(func, sec)
        func()

    t = threading.Timer(sec, func_wrapper)
    t.start()
    return t

# TraceSummary reduces a full trace down to some summary information about it.
class TraceSummary (object):
    def __init__(self, event):
        self.first = 99999999999999999  # Earliest timestamp
        self.last = -99999999999999999  # Latest timestamp
        self.count = 1                  # Number of events in the trace
        self.maxdepth = 0               # Maximum depth of the Lamport clock
        self.category = None            # Category of the earliest call

        self.add(event)

    # Add an event to this trace summary. This mostly means updating our sense
    # of the boundary timestamps as needed.
    def add(self, event):
        timestamp = event.timestamp
        clocks = event.context.clock.clocks

        if timestamp < self.first:
            self.first = timestamp
            self.category = event.category

        if timestamp > self.last:
            self.last = timestamp

        if len(clocks) > self.maxdepth:
            self.maxdepth = len(clocks)

        self.count += 1

    def __str__(self):
        return("%s -- %dms, %d call%s, %d level%s" %
               (self.category, self.last - self.first,
                self.count, "" if (self.count == 1) else "s",
                self.maxdepth, "" if (self.maxdepth == 1) else "s"))

# A TraceSet is a group of TraceSummary objects, with extra logic around periodically
# dumping the summaries of traces we figure are probably complete.
#
# At present we figure that something is complete based on time. We could also do it
# by having the client log something with e.g. a special contentType indicating that
# the trace is finished, and how things went.
class TraceSet (object):
    def __init__(self):
        # traces, sweepsLeft, and swept are all keyed by traceId.
        self.traces = {}            # Trace summaries
        self.sweepsLeft = {}        # Sweep intervals left before we call the trace finished
        self.swept = {}             # Trace IDs we've declared finished

        set_interval(self.sweep, 2) # Sweep every two seconds

    # Add a LogEvent to this TraceSet.
    def add(self, event):
        # Grab the traceId...
        traceId = event.context.traceId

        # If this traceId is marked as swept, we shouldn't do anything else with it.
        if not traceId in self.swept:
            # OK, not yet swept. Do we know about it yet?
            if not traceId in self.traces:
                # Nope. Create a new TraceSummary for it.
                self.traces[traceId] = TraceSummary(event)
            else:
                # We've seen this one before. Add it to the extant TraceSummary.
                self.traces[traceId].add(event)

            # Whether new or not, bump the sweep count to 2. As long as we keep 
            # getting new events for this trace, we won't dump its summary.
            self.sweepsLeft[traceId] = 2

    # Sweep the set of traces and see what should be dumped. If force is True, dump
    # everything (this can be used to clean up before exiting), otherwise only dump
    # things that've been idle long enough to call finished.
    def sweep(self, force=False):
        toSmite = []                # Trace IDs to clean up

        for traceId in self.traces:
            # Any traceId still in sweepsLeft is a candidate for being finished.            
            if traceId in self.sweepsLeft:
                # Is it time yet?
                self.sweepsLeft[traceId] -= 1

                if force or (self.sweepsLeft[traceId] <= 0):
                    # Yup, we've used up all the sweeps we're willing to give this.
                    # Print the summary...
                    print("%s: %s" % (traceId, self.traces[traceId]))

                    # ...mark it swept...
                    self.swept[traceId] = True

                    # ...and remember to smite this traceId.
                    toSmite.append(traceId)

        # Delete all the traces in toSmite from self.traces and self.sweepsLeft.
        for traceId in toSmite:
            del(self.traces[traceId])
            del(self.sweepsLeft[traceId])

    # Stop the world -- which, for us, means to sweep everything immediately.
    def stop(self):
        self.sweep(force=True)

# TraceEventHandler gets handed events from the tracing service and wrangles them
# appropriately.
class TraceEventHandler (object):
    def __init__(self, tracer):
        """ Initialize a TraceEventHandler with a set of args from docopt. """
        self.tracer = tracer
        self.traceSet = TraceSet()

    # Handle incoming events
    def traceEvent(self, event):
        # Only process things with timestamps, just in case.
        if getattr(event, "timestamp", None):
            self.traceSet.add(event)
        else:
            logging.info("Skip %s" % event)

    # Subscribe to receive events from the tracing service
    def subscribe(self):
        # First, subscribe to receive log events as they come in over the wire.
        self.tracer.subscribe(self.traceEvent)

        # Next, fire up the heartbeater.
        set_interval(self.sendHeartBeat, 15)

    # Send a heartbeat
    def sendHeartBeat(self):
        # XXX This is brutal hack. Send a LogAck event, which is a no-op, to 
        # keep the connection alive.
        ack = mdk.mdk_tracing.protocol.LogAck()
        ack.timestamp = time.time() * 1000.0
        self.tracer._client.log(ack);

    # Tear everything down
    def stop(self):
        # Dump anything still not dumped...
        self.traceSet.stop()

        # ...and tear down the tracer itself.
        self.tracer.stop()

# Finally! The main event.
def main():
    # Create a new Tracer...
    tracer = mdk.mdk_tracing.Tracer(mdk_runtime.defaultRuntime())

    # ...and a new TraceEventHandler around it.
    traceEventHandler = TraceEventHandler(tracer)

    # Then, register to be fed log events.
    traceEventHandler.subscribe()
  
# START OF SCRIPT
if __name__ == "__main__":
    main()
