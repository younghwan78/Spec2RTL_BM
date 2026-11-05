# round_robin

Implement/repair the synthesizable SystemVerilog module below. Only modify the listed RTL files. Preserve ports and functional behavior described here.

```systemverilog
module round_robin(input clk,rst,accept, input [1:0] req, output [1:0] grant);
```

Two-client round-robin combinational grant with clocked preference. grant=0 if no requests. Single request always granted. Both requests choose preference. Synchronous active-high rst sets preference client 0. On rising clk with accept and a nonzero grant, preference switches to the other client; otherwise hold. Helper choose_grant computes grant. Both files may be edited.

No testbench or simulation system tasks belong in the submitted RTL.
