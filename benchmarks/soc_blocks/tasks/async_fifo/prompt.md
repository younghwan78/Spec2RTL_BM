# async_fifo

Implement `async_fifo`, a dual-clock FIFO of depth 2^AW (AW >= 2) with Gray-coded pointers synchronized through two flip-flops in the destination domain. `wclk` and `rclk` have arbitrary unrelated phase. `wrst_n` and `rrst_n` are asynchronous and active-low; both are asserted together to reset.

- During reset `rempty` is 1 and `wfull` is 0.
- A write is accepted on a rising `wclk` edge when `wr_en && !wfull`; a read on a rising `rclk` edge when `rd_en && !rempty`. Requests while full or empty are ignored.
- `rdata` is first-word-fall-through: while `rempty` is low it shows the oldest entry before the read is issued.
- `wfull` and `rempty` are conservative: the FIFO never overflows or underflows, and data is delivered in order without loss. `wfull` must be high in the cycle directly after the write that fills the FIFO when no read has occurred. `rempty` must be high in the cycle directly after the read that drains it when no write has occurred.
- Flag release is bounded by the synchronizers: after a write into an empty FIFO `rempty` falls within 12 `rclk` cycles, and after a read from a full FIFO `wfull` falls within 12 `wclk` cycles.

Interface:

```systemverilog
module async_fifo #(parameter WIDTH = 8, parameter AW = 3) (
  input wclk, input wrst_n, input wr_en, input [WIDTH-1:0] wdata, output wfull,
  input rclk, input rrst_n, input rd_en, output [WIDTH-1:0] rdata, output rempty
);
```

Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
