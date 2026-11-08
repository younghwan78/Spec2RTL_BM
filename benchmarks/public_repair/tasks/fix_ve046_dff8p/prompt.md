I would like you to implement a module named TopModule with the following
interface. All input and output ports are one bit unless otherwise
specified.

 - input  clk
 - input  reset
 - input  d (8 bits)
 - output q (8 bits)

Implement a module that includes 8 D flip-flops with active high
synchronous reset. The flip-flops must be reset to 0x34 rather than zero.
All DFFs should be triggered by the negative edge of clk.

The module must be named `TopModule`. Provide synthesizable SystemVerilog only; no testbench or simulation system tasks belong in the submitted RTL.


The RTL file provided in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name and ports. Do not rewrite unrelated logic.
