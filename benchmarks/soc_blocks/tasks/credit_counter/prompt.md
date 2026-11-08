# credit_counter

Implement `credit_counter`. MAX >= 1. `rst` is synchronous, active-high, sets `credits` to MAX and clears `overflow`.

- `can_send` is high exactly when `credits != 0`.
- `consume` takes one credit on a rising edge only if `credits != 0`; `consume` while `credits == 0` has no effect.
- `ret` returns one credit on a rising edge.
- An effective consume together with `ret` leaves `credits` unchanged.
- `ret` without an effective consume while `credits == MAX` leaves `credits` at MAX and sets the sticky `overflow` flag, which only `rst` clears.
- At `credits == 0`, `consume` and `ret` in the same cycle yield `credits == 1`.

Interface:

```systemverilog
module credit_counter #(parameter MAX = 8) (
  input clk, input rst,
  input consume, input ret,
  output can_send, output [$clog2(MAX+1)-1:0] credits, output overflow
);
```

Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
