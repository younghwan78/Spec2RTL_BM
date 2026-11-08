Please act as a professional verilog designer.

Implement a module of a carry-lookahead 32-bit adder that uses the Carry-Lookahead Adder (CLA) architecture.

Module name:  
    adder_32bit               
Input ports:
    A[32:1]: 32-bit input operand A.
    B[32:1]: 32-bit input operand B.
Output ports:
    S[32:1]: 32-bit output representing the sum of A and B.
    C32: Carry-out output.

Implementation:
The top module adder_32bit consists of several instances of the 16 bit CLA block you design.

Give me the complete code.

The module must be named `adder_32bit`. Provide synthesizable Verilog only; no testbench or simulation system tasks belong in the submitted RTL.


The RTL file provided in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name and ports. Do not rewrite unrelated logic.
