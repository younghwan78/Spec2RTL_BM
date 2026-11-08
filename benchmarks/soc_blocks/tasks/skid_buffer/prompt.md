# skid_buffer

Implement `skid_buffer`, a two-entry ready/valid pipeline register that breaks the combinational ready path. WIDTH >= 1.

- `rst` is synchronous, active-high and discards all stored beats.
- A beat transfers on the slave side on a rising edge when `s_valid && s_ready`, and on the master side when `m_valid && m_ready`.
- Let occupancy be the number of stored beats, 0 to 2. `m_valid` is high exactly when occupancy >= 1. `s_ready` is high exactly when occupancy < 2.
- `s_ready` must not depend combinationally on `m_ready` or `s_valid`.
- A beat accepted on an edge is visible on `m_valid`/`m_data` in the following cycle when it is the oldest stored beat. Beats leave in the order accepted, with no loss or duplication.
- While `m_valid` is high and `m_ready` is low, `m_data` holds its value. `m_data` is undefined when `m_valid` is low.

Interface:

```systemverilog
module skid_buffer #(parameter WIDTH = 32) (
  input clk, input rst,
  input s_valid, output s_ready, input [WIDTH-1:0] s_data,
  output m_valid, input m_ready, output [WIDTH-1:0] m_data
);
```

Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
