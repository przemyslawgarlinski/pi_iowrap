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
from base import READ_SWITCH_DEBOUNCE
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

        # _MCP23017ListenerThread
        self._read_events_thread = None

        for number in range(1, 17):
            self._ports[number] = Port(self, number)

        self._initialize_ports()

    def __str__(self):
        return 'MCP23017 on address: {}'.format(hex(self._address))

    def __del__(self):
        """Destructor. Tries to gently stop event listening thread."""
        if self._read_events_thread:
            logging.debug(
                'Gently stopping events thread on interface: %s', self)
            self._read_events_thread.stop()

    def _get_events_thread(self):
        """Returns thread that is listening for port value changes.
        
        This method initializes the thread if it not exists and should be 
        always used for getting the listener.
        
        :returns _MCP23017ListenerThread
        """
        if not self._read_events_thread:
            self._read_events_thread = _MCP23017ListenerThread(self)
            self._read_events_thread.run()
        return self._read_events_thread

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

    @property
    def address(self):
        """Returns I2C address for this interface, eg. 0x20."""
        return self._address

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
        listener = self._get_events_thread()
        if on_rising_callback:
            listener.on_rising(self.get_port(port_number), on_rising_callback)
        if on_falling_callback:
            listener.on_falling(self.get_port(port_number), on_falling_callback)

    def clear_read_events(self, port_number):
        listener = self._get_events_thread()
        listener.clear_events(self.get_port(port_number))
        if not listener.has_any_events():
            listener.stop()
            self._read_events_thread = None

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


class _PortListener(object):
    """Take cares of detecting value changes on given port.
    
    It keeps information about port and it's value and all callbacks
    assigned to changes of this value.
    """

    def __init__(self, port):
        self.port = port
        self.last_read_value = port.value
        self._rising_callbacks = []
        self._falling_callbacks = []

    def add_rising_callback(self, callback):
        self._rising_callbacks.append(callback)

    def add_falling_callback(self, callback):
        self._falling_callbacks.append(callback)

    def clear_callbacks(self):
        self._rising_callbacks = []
        self._falling_callbacks = []

    def get_callbacks_to_trigger(self):
        if not self._rising_callbacks and not self._falling_callbacks:
            return []
        to_trigger = []
        new_value = self.port.value
        if new_value != self.last_read_value:
            if (new_value == InOutInterface.HIGH
                and self.last_read_value == InOutInterface.LOW):
                to_trigger.extend(self._rising_callbacks)
            if (new_value == InOutInterface.LOW
                and self.last_read_value == InOutInterface.HIGH):
                to_trigger.extend(self._falling_callbacks)

            self.last_read_value = new_value
        return to_trigger

    def has_changed(self):
        """Return true if port value changed since last read."""
        new_value = self.port.value
        return new_value != self.last_read_value


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

    def __init__(self, interface):
        super(_MCP23017ListenerThread, self).__init__(
            name="Listener on %s" % interface)
        self._interface = interface
        self._listeners_by_port_number = {}

    def on_rising(self, port, callback):
        self._listeners_by_port_number.get(
            port.number, _PortListener(port)
        ).add_rising_callback(callback)

    def on_falling(self, port, callback):
        self._listeners_by_port_number.get(
            port.number, _PortListener(port)
        ).add_falling_callback(callback)

    def clear_events(self, port):
        if port.number in self._listeners_by_port_number:
            self._listeners_by_port_number[port.number].clear_callbacks()

    def has_any_events(self):
        """Returns true if there are any events defined for any port.
        
        If returns false it might be a good indication that this thread
        is no longer needed.
        """
        return bool(self._listeners_by_port_number)

    def stop(self):
        self._stop = True

    def run(self):
        while not self._stop:
            trigger_data_by_port_number = {}
            for port_number, port_listener in (
                    self._listeners_by_port_number.iteritems()):
                callbacks = port_listener.get_callbacks_to_trigger()
                if callbacks:
                    trigger_data_by_port_number[port_number] = (
                        callbacks, port_listener)

            if trigger_data_by_port_number:
                time.sleep(READ_SWITCH_DEBOUNCE / 1000)
                for port_number, trigger_data in (
                        trigger_data_by_port_number.iteritems()):
                    if not self._listeners_by_port_number[port_number].has_changed():
                        for callback in trigger_data[0]:
                            callback(
                                trigger_data[1].port,
                                trigger_data[1].last_read_value
                            )

            time.sleep(0.01)
