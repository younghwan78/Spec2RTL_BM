# counter

Implement/repair the synthesizable SystemVerilog module below. Only modify the listed RTL files. Preserve ports and functional behavior described here.

```systemverilog
module counter(input clk,rst,en, output reg [7:0] count);
```

8-bit counter. On rising clk, synchronous active-high rst clears count. Otherwise en increments modulo 256. Hold when en=0. Reset has priority.

No testbench or simulation system tasks belong in the submitted RTL.
