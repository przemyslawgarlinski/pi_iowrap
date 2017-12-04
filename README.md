# pi_iowrap
Raspberry Pi wrapper for GPIO and MCP23017 extension. It provides common 
interface for using both Pi GPIO and as many MCP23017 extensions as possible.
Since you can have multiple MCP23017 attached with 100+ ports to handle it
would be nice to have some kind of usable library around it. So here it is.

# Installation
Simply clone the repo.

# Setting up
To safely use the code you can use following snippet:
```python
from pi_iowrap.base import cleanup

try:
    # your program here
except:
    # whatever
finally:
    cleanup()
```
The cleanup() will simply do the Pi cleanup for you + do any other necessary
stuff for all created MCP23017.

# The board interface
To make use of MCP23017 extension you must initialize your i2c port in a proper 
way. Additionally you must get to know what is the address of your MCP23017.
The rest will be done by the library.
```python
from pi_iowrap.pi import PiInterface
from pi_iowrap.mcp import MCP23017  
    
pi = PiInterface()
mcp_on_port_0x20 = MCP23017(0x20)
```

From this point using both Raspberry native GPIO as well as MCP23017 can be done
using the same interface, which means the same methods and attributes.
    
Upon creation all ports on given device are set to be output ports
with value set to LOW.

### Getting the port
Ports are numbered 1-based. There is no port with number 0. 
Port is an object of type pi_iowrap.port.Port.
```python
from pi_iowrap.mcp import MCP23017
    
my_interface = MCP23017(0x24)
port1 = my_interface.get_port(1) # The first port on board
all_ports = my_interface.get_all_ports() # Get list of all ports on device
some_ports = my_interface.get_ports(1,2,5) # Get list of port 1, 2 and 5
```

### Checking the port attributes using board interface
There are numerous methods to play with the board interface itself.
Most of them have their representation on Port object instances.

```python
from pi_iowrap.mcp import MCP23017
    
my_interface = MCP23017(0x24)
port1_value = my_interface.get_value(1) # 0 or 1
is_port1_high = my_interface.is_high(1) # true or false
is_port1_low = my_interface.is_low(1) # true or false
is_port1_input = my_interface.is_input(1) # true or false
is_port1_output = my_interface.is_output(1) # true or false
```

### Manipulating port values using board interface
Again all these methods have their representation on Port object instance.
```python
from pi_iowrap.mcp import MCP23017
    
my_interface = MCP23017(0x24)
my_interface.set_high()
my_interface.set_low()
my_interface.set_as_input()
my_interface.set_as_output()
```
NOTE for MCP23017: setting port value is done by setting all GPA or GPB bits 
at once because there is no other way to it. So every time you set a value 
to port there are actually 8 ports values set. When triggering multiple calls 
to *set_high()* or *set_low()* every time all 8 bits are assigned from scratch 
as many times as may calls to *set_high()* or *set_low()* are there.
    
Setting many ports values at once is not supported (yet). So doing it is not
 as fast as it could be. This is a known limitation.

### Listening on port value changes (events) using board interface
You can react upon port value change, it can be either raising or falling.
Raspberry have this functionality available just like that, so this board
interface is just a wrapper. 

For MCP23017 emulation is done. There is one separate thread for every MCP23017 
object created. This thread is listening to any value change on all of the
ports (having separate thread per port would be an overkill).

Each called callback should take 2 parameters:
1. port instance (object)
1. port value (int)

Any port can have multiple event callbacks assigned. These will be triggered
in the order of assignment.

You can clear all events callback assigned to given port. 
You can't clear specific event callbacks.

Some simple examples:
```python
from pi_iowrap.mcp import MCP23017
    
    
def my_custom_rising_callback(port, port_value):
    print 'Detected change from 0 to 1 on port: %s'.format(port)
    
    
def my_custom_falling_callback(port, port_value):
    print 'Detected change from 1 to 0 on port: %s'.format(port)
    
    
my_interface = MCP23017(0x24)
my_interface.set_as_input(5) # Set port 5 as the one reading input.
my_interface.add_event(
    5, 
    on_falling_callback=my_custom_falling_callback,
    on_rising_callback=my_custom_rising_callback)
    
    
# There is another way, plus you can set multiple callbacks
def another_event(port, port_value):
    print 'Port %s value has changed to: %s'.format(port, port_value)
    
my_interface.on_rising_detection(5, another_event)
my_interface.on_falling_detection(5, another_event)
    
# Enough
my_interface.clear_read_events()
```

You can set switch debounce value. It is basically time measured in ms for which
change on port must persist to treat it as a value change. For MCP23017 the value
can't be treated as extremely strict because the port value change is implemented
using python threads. So some delays might happen.
```python
from pi_iowrap.base import Settings
    
Settings.READ_SWITCH_DEBOUNCE = 200 # Milliseconds
```

And again, usually you will want to use Port object directly to trigger all
of these actions.

# Port object
Port object should be the most convenient way to play with outputs/inputs on 
your Pi/MCP23017 board. Have a look at all sample calls:
```python
from pi_iowrap.mcp import MCP23017
    
my_interface = MCP23017(0x24)
port3 = my_interface.get_port(3) # Port object here
    
# Checking the port attributes
port3_number = port3.number # 3
port3_interface = port3.interface # instance of my_interface
port3_value = port3.value # 0 or 1
is_port3_high = port3.is_high # true or false
is_port3_low = port3.is_low # true or false
is_port3_input = port3.is_input # true or false
is_port3_output = port3.is_output # true or false
    
# Some manipulation
port3.set_high()
port3.set_low()
port3.set_as_input()
port3.set_as_output()
    
# Assigning event callbacks
def my_custom_rising_callback(port, port_value):
    print 'Detected change from 0 to 1 on port: %s'.format(port)
    
    
def my_custom_falling_callback(port, port_value):
    print 'Detected change from 1 to 0 on port: %s'.format(port)
    
    
port3.on_falling(my_custom_falling_callback)
port3.on_rising(my_custom_rising_callback)
port3.clear_value_change_listeners()
```