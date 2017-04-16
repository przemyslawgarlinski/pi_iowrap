"""Standard raspberry GPIO access layer.

It defines abstract layer that extends InOutInterface to access all standard
ports on rapsberry pi. It uses RPi.GPIO under the hood.

Thanks to that you have a standardized way of accessing these ports, as well
as any others implementing InOutInterface.
"""


import logging

from base import InOutInterface
from base import get_gpio
from base import Settings
from base import PortListener
from exceptions import InvalidPortNumberError
from port import Port


class PiInterface(InOutInterface):
    """Standard GPIO interface abstraction layer.

    Some examples of raw calls to ports using RPi.GPIO

    GPIO.setmode(GPIO.BOARD) // set usual port numbering
    GPIO.setup(7, GPIO.OUT)
    GPIO.output(7, GPIO.HIGH)
    GPIO.output(7, GPIO.LOW)
    GPIO.cleanup()

    """

    _GROUND = (6, 9, 14, 20, 25, 30, 34, 39)
    _POWER_5V = (2, 4)
    _POWER_3V3 = (1, 17)
    _I2C = (3, 5, 27, 28)
    _FORBIDDEN = _GROUND + _POWER_5V + _POWER_3V3 + _I2C

    PULL_UP = 'pull_up'
    PULL_DOWN = 'pull_down'

    def __init__(self):
        super(PiInterface, self).__init__(40)
        for number in range(1, 41):
            if number not in self._FORBIDDEN:
                self._ports[number] = Port(self, number)

        # Defines the pull up or pull down rezistor for inputs.
        # Possible values are:
        # 1. self.PULL_UP
        # 2. self.PULL_DOWN
        # 3. None (input fluctuating by default)
        self.pull_up_down_rezistor = self.PULL_UP

        self._port_listeners = {}

        self._initialize_ports()

    def __str__(self):
        return 'Raspberry PI GPIO'

    def _validate_port_number(self, port_number):
        super(PiInterface, self)._validate_port_number(port_number)
        if port_number in self._GROUND:
            raise InvalidPortNumberError(
                'This port number(%d) is reserved for GROUND.', port_number)
        if port_number in self._POWER_3V3:
            raise InvalidPortNumberError(
                'This port number(%d) is reserved for 3.3V POWER.', port_number)
        if port_number in self._POWER_5V:
            raise InvalidPortNumberError(
                'This port number(%d) is reserved for 5V POWER.', port_number)
        if port_number in self._I2C:
            raise InvalidPortNumberError(
                'This port number(%d) is reserved for I2c.', port_number)
        if port_number in self._FORBIDDEN:
            raise InvalidPortNumberError(
                'This port number(%d) is forbidden to take.', port_number)

    def _gpio_setup(self, port_number, gpio_attr_name):
        self._validate_port_number(port_number)
        if Settings.IS_NO_HARDWARE_MODE:
            logging.warning('No hardware mode, no value written')
        else:
            gpio = get_gpio()
            if gpio_attr_name == 'IN':
                # Special case for settings port as input.
                # Pullup or pulldown rezistor should be set here.
                kwargs = {}
                if self.pull_up_down_rezistor == self.PULL_UP:
                    kwargs['pull_up_down'] = gpio.PUD_UP
                elif self.pull_up_down_rezistor == self.PULL_DOWN:
                    kwargs['pull_up_down'] = gpio.PUD_DOWN
                gpio.setup(
                    port_number,
                    getattr(gpio, gpio_attr_name),
                    **kwargs)
            else:
                gpio.setup(port_number, getattr(gpio, gpio_attr_name))

    def _gpio_output(self, port_number, value):
        self._validate_port_number(port_number)
        if Settings.IS_NO_HARDWARE_MODE:
            logging.warning('No hardware mode, no value written')
        else:
            gpio = get_gpio()
            gpio.output(
                port_number,
                gpio.HIGH if value == self.HIGH else gpio.LOW
            )

    def get_value(self, port_number):
        self._validate_port_number(port_number)
        value = self._check_no_hardware_port_value(port_number)
        if value is not None:
            return value
        else:
            gpio = get_gpio()
            value = gpio.input(port_number)
            # logging.debug(
            #     'Read gpio port value (%s): %s',
            #     self.get_port(port_number),
            #     value)
            return self.HIGH if value == gpio.HIGH else self.LOW

    def set_as_input(self, port_number):
        self._gpio_setup(port_number, 'IN')
        self._in_out_registry[port_number] = self._INPUT
        return self

    def set_as_output(self, port_number):
        self._gpio_setup(port_number, 'OUT')
        self._in_out_registry[port_number] = self._OUTPUT
        return self

    def set_high(self, port_number):
        self._validate_port_number(port_number)
        self._validate_write_port_number(port_number)
        self._gpio_output(port_number, self.HIGH)
        return self

    def set_low(self, port_number):
        self._validate_port_number(port_number)
        self._validate_write_port_number(port_number)
        self._gpio_output(port_number, self.LOW)
        return self

    def add_event(
            self,
            port_number,
            on_rising_callback=None,
            on_falling_callback=None):
        """Adds listening event on given port.
        
        In this case 2nd argument passed to a callback is a value read
        during callback invocation, which in theory might not be the one
        that actually cause triggering the event.
        """
        if Settings.IS_NO_HARDWARE_MODE:
            logging.warning('No hardware mode, adding read event failed.')
        else:
            port_listener = self._port_listeners.get(port_number)
            if not port_listener:
                port_listener = _PiPortListener(self.get_port(port_number))
                gpio = get_gpio()
                gpio.add_event_detect(
                    port_number,
                    gpio.BOTH,
                    callback=port_listener.trigger_callbacks,
                    bouncetime=Settings.READ_SWITCH_DEBOUNCE)
                self._port_listeners[port_number] = port_listener

            if on_rising_callback:
                logging.debug(
                    'Adding rising callback for interface (%s) on port %d',
                    self, port_number)
                port_listener.add_rising_callback(on_rising_callback)
            if on_falling_callback:
                logging.debug(
                    'Adding falling callback for interface (%s) on port %d',
                    self, port_number)
                port_listener.add_falling_callback(on_falling_callback)

    def clear_read_events(self, port_number):
        if not Settings.IS_NO_HARDWARE_MODE:
            get_gpio().remove_event_detect(port_number)
            if port_number in self._port_listeners:
                del self._port_listeners[port_number]


class _PiPortListener(PortListener):
    def get_callbacks_to_trigger(self):
        if not self._rising_callbacks and not self._falling_callbacks:
            return []
        to_trigger = []
        port_value = self.port.value
        if (port_value == InOutInterface.HIGH):
            to_trigger.extend(self._rising_callbacks)
            logging.debug(
                'Event detected on interface (%s) on port (%d). '
                'Type: RISING.',
                self.port.interface,
                self.port.number)
        elif (port_value == InOutInterface.LOW):
            to_trigger.extend(self._falling_callbacks)
            logging.debug(
                'Event detected on interface (%s) on port (%d). '
                'Type: FALLING.',
                self.port.interface,
                self.port.number)

        return to_trigger