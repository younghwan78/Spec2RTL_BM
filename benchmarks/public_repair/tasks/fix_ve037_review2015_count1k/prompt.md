I would like you to implement a module named TopModule with the following
interface. All input and output ports are one bit unless otherwise
specified.

 - input  clk
 - input  reset
 - output q (10 bits)

The module should implement a counter that counts from 0 to 999,
inclusive, with a period of 1000 cycles. Assume all sequential logic is
triggered on the positive edge of the clock. The reset input is active
high synchronous, and should reset the counter to 0.

The module must be named `TopModule`. Provide synthesizable SystemVerilog only; no testbench or simulation system tasks belong in the submitted RTL.


The RTL file provided in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name and ports. Do not rewrite unrelated logic.
