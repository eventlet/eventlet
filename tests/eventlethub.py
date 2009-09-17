# Copyright (c) 2009 Linden Lab, AG Projects
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import logging

from nose.plugins.base import Plugin
from eventlet import api

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
        
    def beforeContext(self):
        """Select the desired hub.
        """        
        if self.hub_name is None:
            log.warn('Using default eventlet hub: %s, did you mean '\
                     'to supply --hub command line argument?', 
                     api.get_hub().__module__)
        else:
            if self.hub_name == 'twistedr':
                if self.twisted_already_used:
                    return
                else:
                    self.twisted_already_used = True 
            api.use_hub(self.hub_name)
            log.info('using hub %s', api.get_hub())
 