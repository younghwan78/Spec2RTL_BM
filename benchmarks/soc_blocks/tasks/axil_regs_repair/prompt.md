# axil_regs

Implement `axil_regs`, an AXI4-Lite slave with four 32-bit read/write registers. `aresetn` is synchronous, active-low and clears the registers and all channel state.

- Register index is `addr[3:2]`; `addr[1:0]` is ignored. All responses are OKAY (`2'b00`).
- The write address and write data channels are independent: either may complete its handshake first, or both together, with any delay between them, and the write must still complete.
- At most one write and one read are outstanding. While `bvalid` is high, `awready` and `wready` are low. While `rvalid` is high, `arready` is low. Handshake waits must be bounded: after the master presents a channel while no earlier transaction of that kind is outstanding, the slave completes the handshake within a few cycles.
- A write updates only the bytes selected by `wstrb` of the addressed register. After both channels complete, `bvalid` rises within a few cycles and holds with stable `bresp` until `bready` is high on a rising edge, then falls on the next cycle.
- After a read address handshake, `rvalid` rises within a few cycles and holds with stable `rdata`/`rresp` until `rready` is high on a rising edge, then falls on the next cycle.
- A read returns the register's contents as of its address handshake. Reads to a different register concurrent with a write are independent of that write.

Interface:

```systemverilog
module axil_regs (
  input aclk, input aresetn,
  input [3:0] awaddr, input awvalid, output awready,
  input [31:0] wdata, input [3:0] wstrb, input wvalid, output wready,
  output [1:0] bresp, output bvalid, input bready,
  input [3:0] araddr, input arvalid, output arready,
  output [31:0] rdata, output [1:0] rresp, output rvalid, input rready
);
```

The RTL file in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name, parameters and ports, and do not rewrite unrelated logic.


Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
