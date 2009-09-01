import logging

from nose.plugins.base import Plugin
from eventlet import api

log = logging.getLogger('nose.plugins.eventlet_hub')


class EventletHub(Plugin):
    name = 'eventlethub'

    def options(self, parser, env):
        super(EventletHub, self).options(parser, env)
        parser.add_option('--eventlet-hub',
                          dest="eventlet_hub",
                          metavar="HUB",
                          default=env.get('NOSE_EVENTLET_HUB'),
                          help="Use the specified eventlet hub for the tests."\
                           " [NOSE_EVENTLET_HUB]")
                           
    def configure(self, options, config):
        super(EventletHub, self).configure(options, config)
        self.hub_name = options.eventlet_hub
        
    def help(self):
        return "Allows selection of a specific eventlet hub via the "\
        "--eventlet-hub command-line option.  If no hub is explicitly "\
        " specified, the default hub for the current configuration is printed "\
        " and used."
        
        
    def beforeContext(self):
        """Select the desired hub.
        """
        if self.hub_name is None:
            log.warn('using *default* eventlet hub: %s', api.get_hub())
        else:
            try:
                api.use_hub(self.hub_name)
                log.info('using hub %s', api.get_hub())
            except ImportError, ex:
                log.exception('eventlet hub %s not importing', self.hub_name)        
