"""Standard raspberry GPIO access layer.

It defines abstract layer that extends InOutInterface to access all standard
ports on rapsberry pi. It uses RPi.GPIO under the hood.

Thanks to that you have a standardized way of accessing these ports, as well
as any others implementing InOutInterface.
"""


import logging

from base import InOutInterface
from base import get_gpio
from base import IS_NO_HARDWARE_MODE
from base import READ_SWITCH_DEBOUNCE
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

    def __init__(self):
        super(PiInterface, self).__init__(40)
        for number in range(1, 41):
            if number not in self._FORBIDDEN:
                self._ports[number] = Port(self, number)

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
        if IS_NO_HARDWARE_MODE:
            logging.warning('No hardware mode, no value written')
        else:
            gpio = get_gpio()
            gpio.setup(port_number, getattr(gpio, gpio_attr_name))

    def _gpio_output(self, port_number, value):
        self._validate_port_number(port_number)
        if IS_NO_HARDWARE_MODE:
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

    def _add_event(self, port, gpio_mode, callback):
        if IS_NO_HARDWARE_MODE:
            logging.warning('No hardware mode, adding read event failed.')
        else:

            def gpio_callback(*unused_args):
                callback(port, port.value)

            gpio = get_gpio()
            gpio.add_event_detect(
                port.number,
                gpio_mode,
                callback=gpio_callback,
                bouncetime=READ_SWITCH_DEBOUNCE)

    def add_event(
            self,
            port_number,
            on_rising_callback=None,
            on_falling_callback=None):
        if IS_NO_HARDWARE_MODE:
            logging.warning('No hardware mode, adding read event failed.')
        else:
            gpio = get_gpio()
            port = self.get_port(port_number)
            if on_rising_callback:
                self._add_event(
                    port,
                    gpio.RISING,
                    on_rising_callback)
                logging.debug(
                    'Added rising callback (%s) for interface (%d) on port %d',
                    on_rising_callback, self, port_number)
            if on_falling_callback:
                self._add_event(
                    port,
                    gpio.FALLING,
                    on_falling_callback)
                logging.debug(
                    'Added falling callback (%s) for interface (%d) on port %d',
                    on_falling_callback, self, port_number)

    def clear_read_events(self, port_number):
        if not IS_NO_HARDWARE_MODE:
            get_gpio().remove_event_detect(port_number)
