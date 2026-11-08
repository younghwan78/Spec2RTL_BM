I would like you to implement a module named TopModule with the following
interface. All input and output ports are one bit unless otherwise
specified.

 - input  clk
 - input  d
 - output q

A dual-edge triggered flip-flop is triggered on both edges of the clock.
However, FPGAs don't have dual-edge triggered flip-flops, and using an
always @(posedge clk or negedge clk) is not accepted as a legal
sensitivity list. Build a circuit that functionally behaves like a
dual-edge triggered flip-flop.

The module must be named `TopModule`. Provide synthesizable SystemVerilog only; no testbench or simulation system tasks belong in the submitted RTL.


The RTL file provided in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name and ports. Do not rewrite unrelated logic.
