"""Input/output interface read/write layer base definitions.

It defines abstract class for the io interface on raspberry plus some
module function for getting RPi.GPIO and SMBus.
"""

import logging
from exceptions import InvalidPortNumberError


# When set to True smbus libs are not needed and all calls are mocked,
# which means the module will work but with no results. It will send logs.
IS_NO_HARDWARE_MODE = False

# When set to True and IS_NO_HARDWARE_MODE is set to True, the program will
# ask for value of the port when trying to read from it (let's say it is
# full emulation).
NO_HARDWARE_ASK_INPUT = False

# Time (ms) that value change on port must persist to treat it as value change.
READ_SWITCH_DEBOUNCE = 200

_GPIO = None
_BUS = None


def _initialize_pi_libs():
    global _BUS
    global _GPIO
    try:
        from smbus import SMBus
        import RPi.GPIO as GPIO
        _BUS = SMBus(1)
        _GPIO = GPIO
        GPIO.setmode(GPIO.BOARD)
    except ImportError:
        # When running in "NO HARDWARE" mode allow to not have smbus library
        if not IS_NO_HARDWARE_MODE:
            raise


def get_bus():
    global _BUS
    if not _BUS and not IS_NO_HARDWARE_MODE:
        _initialize_pi_libs()
    return _BUS


def get_gpio():
    global _GPIO
    if not _GPIO and not IS_NO_HARDWARE_MODE:
        _initialize_pi_libs()
    return _GPIO


def cleanup():
    if not IS_NO_HARDWARE_MODE:
        get_gpio().cleanup()


class InOutInterface(object):
    """Abstract interface class.

    An interface should be understand as a controller of some number
    of specific ports.

    All ports are 1-based indexed (for the sake of gpio docs).
    """

    # Specifies input and output values used in underneath registry for
    # tracking.
    _INPUT = 'INPUT'
    _OUTPUT = 'OUTPUT'

    # Specifies high and low port values used in underneath registry for
    # tracking
    HIGH = 1
    LOW = 0

    def __init__(self, ports_count):
        # List of ports, filled with None values.
        # Ports should be 1-based indexed therefore the number of elements is
        # ports_count + 1, port with index 0 is not used.
        # The proper ports should be initialized in derived classes.
        self._ports = [None] * (ports_count + 1)

        # Tracks information of which port is treated as input or output.
        # After port initialization all values should be either
        # self._INPUT or self._OUTPUT.
        # 1-based indexed.
        self._in_out_registry = [None] * (ports_count + 1)

    def _initialize_ports(self):
        """Runs through all defined ports and initializes it.

        It should be called after all ports are created, preferably at the
        end of constructor in derived classes.
        """
        for p in self._ports:
            if p:
                p.initialize()

    def _validate_port_number(self, port_number):
        if port_number <= 0:
            raise InvalidPortNumberError(
                'Provided port number(%d) is not greater then 0.', port_number)
        if port_number >= len(self._ports):
            raise InvalidPortNumberError(
                'Provided port number(%d) is greater then highest '
                'port number(%d)', port_number, len(self._ports))

    def _validate_write_port_number(self, port_number):
        if self._in_out_registry[port_number] == self._INPUT:
            raise InvalidPortNumberError(
                'Provided port number(%d) is set as input, can not set value '
                'for it')

    def _validate_listen_port_number(self, port_number):
        if self._in_out_registry[port_number] == self._OUTPUT:
            raise InvalidPortNumberError(
                'Provided port number(%d) is set as output, '
                'can not listen for value on it')

    def _check_no_hardware_port_value(self, port_number):
        """Reads port value in IS_NO_HARDWARE_MODE.

        In case NO_HARDWARE_ASK_INPUT equals False it will always 
        return self._LOW.
        """
        if IS_NO_HARDWARE_MODE:
            logging.warning('No hardware mode, no read can be done.')
            if NO_HARDWARE_ASK_INPUT:
                user_input = raw_input(
                    'Enter value you\'d like your port (%s) to return '
                    '(1 - high, 0 - low): ' % self.get_port(port_number))
                if user_input == "1":
                    return self.HIGH
                else:
                    return self.LOW
            else:
                return self.LOW
        return None

    def get_port(self, port_number):
        """Returns port.

        :rtype: Port
        """
        self._validate_port_number(port_number)
        return self._ports[port_number]

    def get_value(self, port_number):
        """Returns either self._HIGH or self._LOW."""
        raise NotImplementedError

    def is_high(self, port_number):
        self._validate_port_number(port_number)
        return self.get_value(port_number) == self.HIGH

    def is_low(self, port_number):
        self._validate_port_number(port_number)
        return self.get_value(port_number) == self.LOW

    def is_output(self, port_number):
        self._validate_port_number(port_number)
        return self._in_out_registry[port_number] == self._OUTPUT

    def is_input(self, port_number):
        self._validate_port_number(port_number)
        return self._in_out_registry[port_number] == self._INPUT

    def set_high(self, port_number):
        raise NotImplementedError

    def set_low(self, port_number):
        raise NotImplementedError

    def set_as_output(self, port_number):
        raise NotImplementedError

    def set_as_input(self, port_number):
        raise NotImplementedError

    def add_event(
            self,
            port_number,
            on_rising_callback=None,
            on_falling_callback=None):
        """Adds event that should be trigger on port value change.
        
        Callbacks are triggered with following arguments:
        1. Port object
        2. Current port value
        """
        raise NotImplementedError

    def on_rising_detection(self, port_number, callback):
        self.add_event(
            port_number,
            on_rising_callback=callback,
            on_falling_callback=None)

    def on_falling_detection(self, port_number, callback):
        self.add_event(
            port_number,
            on_rising_callback=None,
            on_falling_callback=callback)

    def clear_read_events(self, port_number):
        raise NotImplementedError
