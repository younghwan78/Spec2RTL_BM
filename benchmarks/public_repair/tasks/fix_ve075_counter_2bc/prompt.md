I would like you to implement a module named TopModule with the following
interface. All input and output ports are one bit unless otherwise
specified.

 - input  clk
 - input  areset
 - input  train_valid
 - input  train_taken
 - output state (2 bits)

The module should implement a two-bit saturating counter. The counter
increments (up to a maximum of 3) when train_valid = 1 and
train_taken = 1. It decrements (down to a minimum of 0) when
train_valid = 1 and train_taken = 0. When not training (train_valid = 0),
the counter keeps its value unchanged. areset is a positive edge
triggered asynchronous reset that resets the counter to weakly not-taken
(2'b01). Output state[1:0] is the two-bit counter value. Assume all
sequential logic is triggered on the positive edge of the clock.

The module must be named `TopModule`. Provide synthesizable SystemVerilog only; no testbench or simulation system tasks belong in the submitted RTL.


The RTL file provided in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name and ports. Do not rewrite unrelated logic.
