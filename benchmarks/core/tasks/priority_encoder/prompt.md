# priority_encoder

Implement/repair the synthesizable SystemVerilog module below. Only modify the listed RTL files. Preserve ports and functional behavior described here.

```systemverilog
module priority_encoder(input [7:0] req, output reg [2:0] index, output valid);
```

Combinational 8-bit request. valid=|req. index is the lowest numbered set bit, and zero if req=0. Width fixed at 8.

No testbench or simulation system tasks belong in the submitted RTL.
