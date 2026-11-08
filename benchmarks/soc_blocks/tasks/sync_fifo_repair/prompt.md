# sync_fifo

Implement `sync_fifo`, a single-clock first-word-fall-through FIFO. Supported parameters: WIDTH >= 1, DEPTH >= 2; DEPTH need not be a power of two.

- `rst` is synchronous, active-high and empties the FIFO. It has priority over everything else.
- `full` is high exactly when `count == DEPTH`; `empty` is high exactly when `count == 0`. Both are outputs of current state, with no combinational dependence on `wr_en`/`rd_en`.
- A write is accepted on a rising edge if and only if `wr_en && !full`. A read is accepted if and only if `rd_en && !empty`.
- A write is refused while full even if a read is accepted in the same cycle. A read is refused while empty even if a write is accepted in the same cycle (no fall-through in the empty cycle).
- `rd_data` shows the oldest entry whenever `empty` is low, before the read is issued, and is undefined when empty.
- `count` is the number of stored entries. A simultaneous accepted read and write leaves it unchanged and preserves order.

Interface:

```systemverilog
module sync_fifo #(parameter WIDTH = 8, parameter DEPTH = 4) (
  input clk, input rst,
  input wr_en, input [WIDTH-1:0] wr_data, output full,
  input rd_en, output [WIDTH-1:0] rd_data, output empty,
  output [$clog2(DEPTH+1)-1:0] count
);
```

The RTL file in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name, parameters and ports, and do not rewrite unrelated logic.


Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
