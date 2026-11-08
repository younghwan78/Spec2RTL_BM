# mul_pipe

Implement `mul_pipe`, a signed 16x16 multiplier with exactly three pipeline stages. `rst` is synchronous and active-high; it clears the valid bits of all stages. `p` is two's complement.

- When `en` is high on a rising edge, all three stages advance together and `in_valid`, `a` and `b` are sampled. When `en` is low, every stage holds, including valid bits.
- An input sampled on enabled edge E appears with `out_valid` high after enabled edge E+2, i.e. it is visible in the cycle after the third enabled edge that includes E, with `p == a * b` as signed values.
- `p` is only defined while `out_valid` is high.

Interface:

```systemverilog
module mul_pipe (
  input clk, input rst, input en, input in_valid,
  input signed [15:0] a, input signed [15:0] b,
  output out_valid, output signed [31:0] p
);
```

Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
