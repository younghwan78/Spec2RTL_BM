# fifo

Implement/repair the synthesizable SystemVerilog module below. Only modify the listed RTL files. Preserve ports and functional behavior described here.

```systemverilog
module fifo(input clk,rst,in_valid, input [7:0] in_data, output in_ready, input out_ready, output out_valid, output [7:0] out_data);
```

Two-entry 8-bit synchronous FIFO. Synchronous active-high rst empties FIFO. out_valid=(occupancy>0); in_ready=(occupancy<2), including when full and pop asserted. Transfers occur only valid&&ready. out_data is oldest entry when valid; undefined otherwise. Simultaneous push/pop preserve order and occupancy. No fall-through.

No testbench or simulation system tasks belong in the submitted RTL.
