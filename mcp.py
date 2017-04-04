"""MCP23017 io interface.
 
Allows to operate on MCP23017 microcontroller that allows to extend number
of io ports on raspberry. This class creates additional access layer 
that extends InOutInterface. Thanks to that you can use all additional
ports in a standardized way. It uses SMBus under the hood.
"""


import logging
import threading
import time

from base import InOutInterface
from base import IS_NO_HARDWARE_MODE
from base import get_bus
from port import Port

from exceptions import Error


class MCP23017(InOutInterface):
    """Defines interface created by using MCP23017.

    When using MCP23017 controller you can get new 16 in/out ports.
    This class provides an abstraction layer to easily control these ports
    together with standard raspberry gpio ones.

    Everywhere port number is understood as int between 1-16. Distinction on
    GPA and GPB is done either by specific public methods or internally
    (when needing specific register).

    Some examples for raw port value set when using SMBus:

    Set all GPA pins of 0x20 as output
    > bus.write_byte_data(0x20, 0x00, 0)

    Set all GPB pins of 0x20 as output
    > bus.write_byte_data(0x20, 0x01, 0)

    Set all GPA pins of 0x20 to LOW
    > bus.write_byte_data(0x20, 0x14, 0)

    Set all GPB pins of 0x20 to LOW
    > bus.write_byte_data(0x20, 0x15, 0)

    Set first port of GPA to HIGH
    > bus.write_byte_data(0x20, 0x14, 0b00000001)
    > bus.write_byte_data(0x20, 0x14, int("0b00000001", 2))

    Set first port of GPB to HIGH
    > bus.write_byte_data(0x20, 0x15, 0b00000001)
    > bus.write_byte_data(0x20, 0x15, int("0b00000001", 2))

    TODO: consider the following:
    To set the value for port all other 7 port values must be read first.
    This is a lot of operations, the state of all ports could be saved
    locally (as it was at the beginning). There is visible slow down because
    of that, but so far it is enough for the needs.
    """

    # Defines names of first and second half of all 16 ports.
    # Sometimes it is preferred to use one interface and it's GPA or GPB part,
    # each containing 8 ports, instead of all 16 ports layer.
    # And of course each part has different registers to be set when setting
    # value to port.
    _PART_A = 'A'
    _PART_B = 'B'

    def __init__(self, address):
        """
        Creates new instance of interface with some address defined by I2C.
        It DOES NOT validate if an interface instance with the same address
        was already created.

        :param address: Address of I2C interface, eg. 0x20.
        """
        super(MCP23017, self).__init__(16)
        self._address = address

        # Dict containing _MCP23017ListenerThread objects. Key is the
        # port number. Only running threads should be kept in this dict.
        self._read_event_threads = {}

        for number in range(1, 17):
            self._ports[number] = Port(self, number)

        self._initialize_ports()

    def __str__(self):
        return 'MCP23017 on address: {}'.format(hex(self._address))

    @property
    def address(self):
        """Returns I2C address for this interface, eg. 0x20."""
        return self._address

    def _get_part(self, port_number):
        return self._PART_A if port_number <= 8 else self._PART_B

    def _get_write_register(self, port_number):
        """Returns write register for given port.

        There is different register for GPA and GPB.
        """
        part = self._get_part(port_number)
        if part == self._PART_A:
            return 0x14
        elif part == self._PART_B:
            return 0x15

    def _get_read_register(self, port_number):
        """Returns write register for given port.

        There is different register for GPA and GPB.
        """
        part = self._get_part(port_number)
        if part == self._PART_A:
            return 0x12
        elif part == self._PART_B:
            return 0x13

    def _get_setas_register(self, port_number):
        """Returns <setas> register for given port.

        Setas register is the one under which port can be defined as input
        or output. There is different register for GPA and GPB.
        """
        part = self._get_part(port_number)
        if part == self._PART_A:
            return 0x00
        elif part == self._PART_B:
            return 0x01

    def _get_binary_string_for_value(
            self,
            port_number,
            value,
            siblings_value_getter):
        """Return binary string for GP ports part.

        It takes given value for given port, reads all other ports on given
        GP ports part (either GPA or GPB) and returns binary string ready
        to be written to the BUS.

        siblings_value_getter is a tricky part, because this argument should
        contain lambda function that should take Port object as argument
        and return proper value for the given port (either self._HIGH or
        self._LOW).

        :param port_number: port number
        :param value: either self._HIGH or self._LOW
        :param siblings_value_getter: lambda function
        :return: string with binary representation of new value

        """
        # ports = None
        part = self._get_part(port_number)
        start_port_number = 1
        if part == self._PART_B:
            start_port_number = 9

        binary_value = []
        for number in range(start_port_number, start_port_number + 8):
            if number == port_number:
                binary_value.append('1' if value == self.HIGH else '0')
            else:
                binary_value.append(
                    '1' if siblings_value_getter(
                        self._ports[number]) == self.HIGH
                    else '0')

        return '0b%s' % ''.join(reversed(binary_value))

    def _set_value(
            self,
            port_number,
            register,
            value,
            siblings_value_getter):

        binary_str_to_write = self._get_binary_string_for_value(
            port_number,
            value,
            siblings_value_getter)
        logging.debug(
            'Writing to interface %s on register %s value %s',
            str(self),
            hex(register),
            binary_str_to_write
        )

        if IS_NO_HARDWARE_MODE:
            logging.warning('No hardware mode, no write done.')
        else:
            get_bus().write_byte_data(
                self._address,
                register,
                int(binary_str_to_write, 2)
            )

    def get_value(self, port_number):
        """Return value read from port.

        It can be used both for input and output ports.

        The port value is read in the same manner it is written to.
        The whole 8-bit registry is read, converted to binary string,
        and value for given port is read from it.
        """
        self._validate_port_number(port_number)
        value = self._check_no_hardware_port_value(port_number)
        if value is not None:
            return value
        else:
            value = get_bus().read_byte_data(
                self._address,
                self._get_read_register(port_number)
            )
            # Decode. Incoming binary value represent the whole 8 bit register.
            # So format the number to be binary representation without
            # '0b' prefix, revert it and get the port value.

            # logging.debug(
            #     'Reading value for port %s -> %s',
            #     self.get_port(port_number),
            #     format(value, '#010b'))
            index = (port_number - 1) % 8
            value = format(value, '08b')[::-1][index]
            if value == '0':
                return self.LOW
            elif value == '1':
                return self.HIGH
            else:
                # This actually should never happen.
                raise Error(
                    'Could not read value for port %s',
                    self.get_port(port_number))

    def set_high(self, port_number):
        self._validate_port_number(port_number)
        self._validate_write_port_number(port_number)
        self._set_value(
            port_number,
            self._get_write_register(port_number),
            self.HIGH,
            lambda x: self.HIGH if x.is_high else self.LOW
        )
        return self

    def set_low(self, port_number):
        self._validate_port_number(port_number)
        self._validate_write_port_number(port_number)
        self._set_value(
            port_number,
            self._get_write_register(port_number),
            self.LOW,
            lambda x: self.HIGH if x.is_high else self.LOW
        )
        return self

    def set_as_input(self, port_number):
        self._validate_port_number(port_number)
        self._set_value(
            port_number,
            self._get_setas_register(port_number),
            self.HIGH,
            lambda x: self.HIGH if x.is_input else self.LOW
        )
        self._in_out_registry[port_number] = self._INPUT
        return self

    def set_as_output(self, port_number):
        self._validate_port_number(port_number)
        self._set_value(
            port_number,
            self._get_setas_register(port_number),
            self.LOW,
            lambda x: self.HIGH if x.is_input else self.LOW
        )

        self._in_out_registry[port_number] = self._OUTPUT
        self.clear_read_events(port_number)
        return self

    def add_event(
            self,
            port_number,
            on_rising_callback=None,
            on_falling_callback=None):
        self._validate_listen_port_number(port_number)
        listener = self._read_event_threads.get(port_number)
        if not listener:
            listener = _MCP23017ListenerThread(self.get_port(port_number))
            listener.start()
        if on_rising_callback:
            listener.rising_callbacks.append(on_rising_callback)
        if on_falling_callback:
            listener.falling_callbacks.append(on_falling_callback)

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
        listener = self._read_event_threads.get(port_number)
        if listener:
            listener.stop()
            del self._read_event_threads[port_number]

    def is_high_gpa(self, port_number):
        return self.is_high(port_number)

    def is_high_gpb(self, port_number):
        return self.is_high(port_number + 8)

    def is_low_gpa(self, port_number):
        return self.is_low(port_number)

    def is_low_gpb(self, port_number):
        return self.is_low(port_number + 8)

    def set_high_gpa(self, port_number):
        return self.set_high(port_number)

    def set_high_gpb(self, port_number):
        return self.set_high(port_number + 8)

    def set_low_gpa(self, port_number):
        return self.set_low(port_number)

    def set_low_gpb(self, port_number):
        return self.set_low(port_number + 8)

    def set_as_output_gpa(self, port_number):
        return self.set_as_output(port_number)

    def set_as_output_gpb(self, port_number):
        return self.set_as_output(port_number + 8)

    def set_as_input_gpa(self, port_number):
        return self.set_as_input(port_number)

    def set_as_input_gpb(self, port_number):
        return self.set_as_input(port_number + 8)

    def get_port_gpa(self, port_number):
        return self.get_port(port_number)

    def get_port_gpb(self, port_number):
        return self.get_port(port_number + 8)


class _MCP23017ListenerThread(threading.Thread):
    """Thread used for listening on MCP23017 ports.

    As reading on this i2c extension must be somehow made, separate thread
    should be created to monitor the ports.

    It allows to register multiple callbacks for port that will be triggered
    when the value on port changes from low to high or vice versa.

    Each callback will be triggered with two arguments:
    1. port instance
    2. value read from port that triggered the callback (this should be equal
    to the one read from port afterwards, but who knows, lags might happen).
    """

    # Time (seconds) that value change must persist to trigger callback.
    SWITCH_DEBOUNCE = 0.2

    def __init__(self, port, rising_callback=None, falling_callback=None):
        """

        :param port: Port instance
        :param rising_callback: function or None,
        :param falling_callback: 
        """
        super(_MCP23017ListenerThread, self).__init__(
            name="Listener on %s" % port)
        self.rising_callbacks = []
        if rising_callback:
            self.rising_callbacks.append(rising_callback)
        self.falling_callbacks = []
        if falling_callback:
            self.falling_callbacks.append(falling_callback)
        self._port = port
        self._value = None
        self._stop = False
        # Make it a deamon so whole program should not wait for it to terminate.
        self.setDaemon(True)

    def stop(self):
        self._stop = True

    def run(self):
        self._value = self._port.value
        while not self._stop:
            to_trigger = []
            new_value = self._port.value
            if (new_value == InOutInterface.HIGH
                and self._value == InOutInterface.LOW):
                to_trigger.extend(self.rising_callbacks)
            if (new_value == InOutInterface.LOW
                and self._value == InOutInterface.HIGH):
                to_trigger.extend(self.falling_callbacks)

            if to_trigger:
                time.sleep(self.SWITCH_DEBOUNCE)
                if new_value == self._port.value:
                    logging.debug(
                        'Port %s changed state (%s->%s).',
                        self._port,
                        self._value,
                        new_value)
                    self._value = new_value
                    for callback in to_trigger:
                        callback(self._port, new_value)
            else:
                self._value = new_value

            time.sleep(0.01)

