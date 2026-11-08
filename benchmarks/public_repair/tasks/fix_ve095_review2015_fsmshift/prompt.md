I would like you to implement a module named TopModule with the following
interface. All input and output ports are one bit unless otherwise
specified.

 - input  clk
 - input  reset
 - output shift_ena

This module is a part of the FSM for controlling a shift register, we
want the ability to enable the shift register for exactly 4 clock cycles
whenever the proper bit pattern is detected. Whenever the FSM is reset,
assert shift_ena for 4 cycles, then 0 forever (until reset). Reset should
be active high synchronous.

Assume all sequential logic is triggered on the positive edge of the
clock.

The module must be named `TopModule`. Provide synthesizable SystemVerilog only; no testbench or simulation system tasks belong in the submitted RTL.


The RTL file provided in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name and ports. Do not rewrite unrelated logic.
