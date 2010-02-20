import logging

from nose.plugins.base import Plugin
from eventlet import hubs

log = logging.getLogger('nose.plugins.eventlethub')

class EventletHub(Plugin):
    name = 'eventlethub'

    def options(self, parser, env):
        super(EventletHub, self).options(parser, env)
        parser.add_option('--hub',
                          dest="eventlet_hub",
                          metavar="HUB",
                          default=env.get('NOSE_EVENTLET_HUB'),
                          help="Use the specified eventlet hub for the tests."\
                           " [NOSE_EVENTLET_HUB]")
        parser.add_option('--reactor',
                          dest="eventlet_reactor",
                          metavar="REACTOR",
                          default=env.get('NOSE_EVENTLET_REACTOR'),
                          help="Use the specified Twisted reactor for the "\
                          "tests.  Use of this flag forces the twisted hub, "\
                          "as if --hub=twistedr was also supplied. "\
                          "[NOSE_EVENTLET_REACTOR]")

                           
    def configure(self, options, config):
        super(EventletHub, self).configure(options, config)
        if options.eventlet_reactor is not None:
            self.hub_name = 'twistedr'
            self.reactor = options.eventlet_reactor
        else:
            self.hub_name = options.eventlet_hub
            self.reactor = None
            
        if self.hub_name == 'twistedr':
            self.twisted_already_used = False
            if self.reactor is None:
                raise ValueError("Can't have twisted hub without specifying a "\
                "reactor.  Use --reactor instead.")

            m = __import__('twisted.internet.' + self.reactor)
            getattr(m.internet, self.reactor).install()
        
    def help(self):
        return "Allows selection of a specific eventlet hub via the "\
        "--eventlet-hub command-line option.  If no hub is explicitly "\
        " specified, the default hub for the current configuration is printed "\
        " and used."
        
    def begin(self):
        """Select the desired hub.
        """        
        if self.hub_name is None:
            log.warn('Using default eventlet hub: %s, did you mean '\
                     'to supply --hub command line argument?', 
                     hubs.get_hub().__module__)
        else:
            if self.hub_name == 'twistedr':
                if self.twisted_already_used:
                    return
                else:
                    self.twisted_already_used = True 
            hubs.use_hub(self.hub_name)
            log.info('using hub %s', hubs.get_hub())
 