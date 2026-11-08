I would like you to implement a module named TopModule with the following
interface. All input and output ports are one bit unless otherwise
specified.

 - input  clk
 - input  reset
 - input  data
 - output start_shifting

The module should implement a finite-state machine that searches for the
sequence 1101 in an input bit stream. When the sequence is found, it
should set start_shifting to 1, forever, until reset. Reset is active
high synchronous. Assume all sequential logic is triggered on the
positive edge of the clock.

The module must be named `TopModule`. Provide synthesizable SystemVerilog only; no testbench or simulation system tasks belong in the submitted RTL.


The RTL file provided in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name and ports. Do not rewrite unrelated logic.
