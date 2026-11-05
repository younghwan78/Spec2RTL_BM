# saturating_add

Implement/repair the synthesizable SystemVerilog module below. Only modify the listed RTL files. Preserve ports and functional behavior described here.

```systemverilog
module saturating_add(input [7:0] a,b, output [7:0] y, output overflow);
```

Unsigned 8-bit combinational addition. y=min(a+b,255); overflow is one iff a+b>255. No clock/reset. Width fixed at 8.

No testbench or simulation system tasks belong in the submitted RTL.
