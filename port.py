"""Defines single port on raspberry pi.

Because it is a composition of an interface it belongs to, it is more 
like a proxy for commands that are sent from single port to gpio.
"""


import logging


class Port(object):
    def __init__(self, interface, number):
        self._interface = interface
        self._number = number

    def initialize(self):
        self.set_as_output()
        self.set_low()

    def __str__(self):
        return 'Port id: {} on interface: {}'.format(
            self._number, self._interface)

    @property
    def number(self):
        return self._number

    @property
    def value(self):
        return self._interface.get_value(self._number)

    @property
    def is_high(self):
        return self._interface.is_high(self._number)

    @property
    def is_low(self):
        return self._interface.is_low(self._number)

    @property
    def is_output(self):
        return self._interface.is_output(self._number)

    @property
    def is_input(self):
        return self._interface.is_input(self._number)

    def set_as_output(self):
        logging.debug('Setting as output: %s', str(self))
        self._interface.set_as_output(self._number)
        return self

    def set_as_input(self):
        logging.debug('Setting as input: %s', str(self))
        self._interface.set_as_input(self._number)
        return self

    def set_high(self):
        logging.debug('Setting high: %s', str(self))
        self._interface.set_high(self._number)
        return self

    def set_low(self):
        logging.debug('Setting low: %s', str(self))
        self._interface.set_low(self._number)
        return self

    def on_falling(self, callback):
        """Adds callback to be fired when value on port changes 1 -> 0.

        Callback will be triggered with two arguments:
        1. port instance
        2. value read from port that triggered the callback
        """
        self._interface.on_falling_detection(self._number, callback)

    def on_rising(self, callback):
        """Adds callback to be fired when value on port changes 0 -> 1.

        Callback will be triggered with two arguments:
        1. port instance
        2. value read from port that triggered the callback
        """
        self._interface.on_rising_detection(self._number, callback)

    def clear_value_change_listeners(self):
        """Clears all callbacks set with on_falling and on rising methods."""
        self._interface.clear_read_events(self._number)

