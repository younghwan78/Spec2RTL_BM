# apb_regs

Implement `apb_regs`, an APB3 slave register block. `presetn` is synchronous and active-low; it clears every register to zero. All register updates occur on the rising edge of `pclk`.

An access phase is a cycle with `psel && penable`. A cycle with `psel && !penable` is the setup phase and must have no effect. `pready` is always 1.

| paddr | name | behaviour |
|---|---|---|
| 0x00 | CTRL | read/write, bits 7:0; bits 31:8 read as 0; drives `ctrl` |
| 0x04 | STATUS | read-only, `{16'b0, status_in}`; writes are ignored without error |
| 0x08 | IRQ | bits 7:0; write-1-to-clear; drives `irq_pending` |
| 0x0C | SCRATCH | read/write, 32 bits |

Each bit of `irq_set` sets the matching IRQ bit on the rising edge whenever it is high, with or without an APB access. If the same bit is set by `irq_set` and cleared by a write in the same cycle, it ends up set.

`pslverr` is high in an access phase when `paddr[1:0] != 0` or `paddr[7:4] != 0`, and low otherwise, combinationally. Such accesses change nothing. `prdata` shows the addressed register in a read access phase, combinationally, and is 0 in every other cycle, including error reads and write accesses.

Interface:

```systemverilog
module apb_regs (
  input pclk, input presetn,
  input psel, input penable, input pwrite, input [7:0] paddr, input [31:0] pwdata,
  output [31:0] prdata, output pready, output pslverr,
  input [15:0] status_in, input [7:0] irq_set,
  output [7:0] ctrl, output [7:0] irq_pending
);
```

Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
