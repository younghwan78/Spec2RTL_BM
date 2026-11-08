#!/usr/bin/env python3
"""Generate the locally authored SoC-style block suite.

This generator overwrites tasks/ and suite.json. Do not run it for routine validation; review the
diff against any manual edits first. Checkers derive expected behaviour from each prompt.
"""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
LIMIT = 4000000
COMMON_NOTE = ("\n\nSubmit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. "
               "No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.\n")
REPAIR_NOTE = ("\n\nThe RTL file in this workspace was written for the specification above but contains a functional "
               "defect. Repair it so that it fully meets the specification. Keep the module name, parameters and "
               "ports, and do not rewrite unrelated logic.\n")


def bench(decl, body):
    return f"""`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
{decl}
initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
{body}
$display("HWBENCH_PASS");
$finish;
end
initial begin #{LIMIT}; $fatal(1, "bench timeout"); end
endmodule
"""


T = []


def task(name, title, category_domain, difficulty, header, body, spec, checks, bugs, repair=False):
    T.append(dict(name=name, title=title, domain=category_domain, difficulty=difficulty, header=header, body=body,
                  spec=spec, checks=checks, bugs=bugs, repair=repair))


# ---------------------------------------------------------------- sync FIFO
FIFO_DECL = """parameter D = %d; parameter W = 12;
reg clk = 0, rst = 1, wr_en = 0, rd_en = 0; reg [W-1:0] wr_data = 0; wire full, empty; wire [W-1:0] rd_data; wire [$clog2(D+1)-1:0] count;
sync_fifo #(.WIDTH(W), .DEPTH(D)) dut(clk, rst, wr_en, wr_data, full, rd_en, rd_data, empty, count);
always #5 clk = ~clk;
reg [W-1:0] q[0:65535]; integer n = 0, h = 0, t = 0; reg live = 0, p, g;
task step(input r, input w, input [W-1:0] d, input e);
begin
  @(negedge clk); rst = r; wr_en = w; wr_data = d; rd_en = e; #1;
  if (live) begin
    if (full !== (n == D) || empty !== (n == 0) || count !== n) $fatal(1, "flags");
    if (n > 0 && rd_data !== q[h]) $fatal(1, "first-word data");
  end
  p = w && n < D; g = e && n > 0;
  @(posedge clk);
  if (r) begin n = 0; h = 0; t = 0; live = 1; end
  else begin if (g) h = h + 1; if (p) begin q[t] = d; t = t + 1; end n = n + p - g; end
end
endtask
"""
task("sync_fifo", "parameterized first-word-fall-through FIFO", "memory", "medium",
     """module sync_fifo #(parameter WIDTH = 8, parameter DEPTH = 4) (
  input clk, input rst,
  input wr_en, input [WIDTH-1:0] wr_data, output full,
  input rd_en, output [WIDTH-1:0] rd_data, output empty,
  output [$clog2(DEPTH+1)-1:0] count
);""", """  reg [WIDTH-1:0] mem [0:DEPTH-1];
  reg [$clog2(DEPTH)-1:0] wp, rp;
  reg [$clog2(DEPTH+1)-1:0] n;
  wire w = wr_en && !full;
  wire r = rd_en && !empty;
  assign full = n == DEPTH;
  assign empty = n == 0;
  assign count = n;
  assign rd_data = mem[rp];
  always @(posedge clk)
    if (rst) begin n <= 0; wp <= 0; rp <= 0; end
    else begin
      if (w) begin mem[wp] <= wr_data; wp <= (wp == DEPTH-1) ? 0 : wp + 1; end
      if (r) rp <= (rp == DEPTH-1) ? 0 : rp + 1;
      n <= n + w - r;
    end
""", """Implement `sync_fifo`, a single-clock first-word-fall-through FIFO. Supported parameters: WIDTH >= 1, DEPTH >= 2; DEPTH need not be a power of two.

- `rst` is synchronous, active-high and empties the FIFO. It has priority over everything else.
- `full` is high exactly when `count == DEPTH`; `empty` is high exactly when `count == 0`. Both are outputs of current state, with no combinational dependence on `wr_en`/`rd_en`.
- A write is accepted on a rising edge if and only if `wr_en && !full`. A read is accepted if and only if `rd_en && !empty`.
- A write is refused while full even if a read is accepted in the same cycle. A read is refused while empty even if a write is accepted in the same cycle (no fall-through in the empty cycle).
- `rd_data` shows the oldest entry whenever `empty` is low, before the read is issued, and is undefined when empty.
- `count` is the number of stored entries. A simultaneous accepted read and write leaves it unchanged and preserves order.""",
     {"directed": bench(FIFO_DECL % 4, """step(1,0,0,0); for (i=0;i<6;i=i+1) step(0,1,i+1,0); step(0,1,99,1); step(0,1,50,1); for (i=0;i<6;i=i+1) step(0,0,0,1);
step(0,1,7,1); step(0,0,0,0); step(0,1,8,1); step(0,1,9,1); step(1,1,3,1); step(0,0,0,0); step(0,0,0,1);"""),
      "seeded": bench(FIFO_DECL % 5, """step(1,0,0,0); for (i=0;i<1500;i=i+1) step(($random(seed)&127)==0, $random(seed)&1, $random(seed), $random(seed)&1); for (i=0;i<8;i=i+1) step(0,0,0,1);""")},
     [("wrap_binary", [("wp <= (wp == DEPTH-1) ? 0 : wp + 1", "wp <= wp + 1")], ["seeded"]),
      ("count_simultaneous", [("n <= n + w - r;", "n <= n + w - (r && !w);")], ["seeded"]),
      ("write_when_full_read", [("wire w = wr_en && !full;", "wire w = wr_en && (!full || rd_en);")], ["seeded"])], repair=True)

# ---------------------------------------------------------------- skid buffer
SKID_DECL = """reg clk = 0, rst = 1, s_valid = 0, m_ready = 0; reg [31:0] s_data = 0; wire s_ready, m_valid; wire [31:0] m_data;
skid_buffer #(.WIDTH(32)) dut(clk, rst, s_valid, s_ready, s_data, m_valid, m_ready, m_data);
always #5 clk = ~clk;
reg [31:0] q[0:65535]; integer n = 0, h = 0, t = 0; reg live = 0, p, g, held_rdy;
task step(input r, input v, input [31:0] d, input rdy);
begin
  @(negedge clk); rst = r; s_valid = v; s_data = d; m_ready = rdy; #1;
  if (live) begin
    if (s_ready !== (n < 2) || m_valid !== (n > 0)) $fatal(1, "handshake flags");
    if (n > 0 && m_data !== q[h]) $fatal(1, "data");
    held_rdy = s_ready; m_ready = !rdy; #1;
    if (s_ready !== held_rdy) $fatal(1, "s_ready depends combinationally on m_ready");
    m_ready = rdy; #1;
  end
  p = v && n < 2; g = rdy && n > 0;
  @(posedge clk);
  if (r) begin n = 0; h = 0; t = 0; live = 1; end
  else begin if (g) h = h + 1; if (p) begin q[t] = d; t = t + 1; end n = n + p - g; end
end
endtask
"""
task("skid_buffer", "registered ready/valid skid buffer", "interface", "medium",
     """module skid_buffer #(parameter WIDTH = 32) (
  input clk, input rst,
  input s_valid, output s_ready, input [WIDTH-1:0] s_data,
  output m_valid, input m_ready, output [WIDTH-1:0] m_data
);""", """  reg [WIDTH-1:0] out_d, skid_d;
  reg out_v, skid_v;
  assign s_ready = !skid_v;
  assign m_valid = out_v;
  assign m_data = out_d;
  wire out_load = !out_v || m_ready;
  always @(posedge clk)
    if (rst) begin out_v <= 0; skid_v <= 0; end
    else if (out_load) begin
      if (skid_v) begin out_d <= skid_d; out_v <= 1; skid_v <= 0; end
      else begin out_v <= s_valid; if (s_valid) out_d <= s_data; end
    end
    else if (s_valid && s_ready) begin skid_d <= s_data; skid_v <= 1; end
""", """Implement `skid_buffer`, a two-entry ready/valid pipeline register that breaks the combinational ready path. WIDTH >= 1.

- `rst` is synchronous, active-high and discards all stored beats.
- A beat transfers on the slave side on a rising edge when `s_valid && s_ready`, and on the master side when `m_valid && m_ready`.
- Let occupancy be the number of stored beats, 0 to 2. `m_valid` is high exactly when occupancy >= 1. `s_ready` is high exactly when occupancy < 2.
- `s_ready` must not depend combinationally on `m_ready` or `s_valid`.
- A beat accepted on an edge is visible on `m_valid`/`m_data` in the following cycle when it is the oldest stored beat. Beats leave in the order accepted, with no loss or duplication.
- While `m_valid` is high and `m_ready` is low, `m_data` holds its value. `m_data` is undefined when `m_valid` is low.""",
     {"directed": bench(SKID_DECL, """step(1,0,0,0); step(0,1,11,0); step(0,1,22,0); step(0,1,33,0); step(0,1,33,0); step(0,0,0,1); step(0,1,33,1); step(0,1,44,1); step(0,1,55,1); step(0,0,0,1); step(0,0,0,1); step(0,0,0,0);
step(0,1,66,0); step(1,1,77,0); step(0,0,0,0);"""),
      "seeded": bench(SKID_DECL, """step(1,0,0,0); for (i=0;i<1500;i=i+1) step(($random(seed)&255)==0, $random(seed)&1, $random(seed), $random(seed)&1); for (i=0;i<4;i=i+1) step(0,0,0,1);""")},
     [("comb_ready", [("assign s_ready = !skid_v;", "assign s_ready = !skid_v || m_ready;")], ["directed"]),
      ("skid_data", [("out_d <= skid_d;", "out_d <= s_data;")], ["seeded"]),
      ("lost_beat", [("skid_d <= s_data; skid_v <= 1;", "skid_d <= s_data;")], ["seeded"]),
      ("no_bubble_fill", [("wire out_load = !out_v || m_ready;", "wire out_load = m_ready;")], ["seeded"])], repair=True)

# ---------------------------------------------------------------- APB register block
APB_DECL = """reg clk = 0, rstn = 0, sel = 0, en = 0, wr = 0; reg [7:0] addr = 0; reg [31:0] wd = 0; wire [31:0] rd; wire rdy, err;
reg [15:0] st = 0; reg [7:0] irq = 0; wire [7:0] ctrl, pending;
apb_regs dut(clk, rstn, sel, en, wr, addr, wd, rd, rdy, err, st, irq, ctrl, pending);
always #5 clk = ~clk;
reg [7:0] c_m = 0, i_m = 0; reg [31:0] s_m = 0, want; reg live = 0, acc, ok;
task step(input s, input e, input w, input [7:0] a, input [31:0] d, input [15:0] sv, input [7:0] iv);
begin
  @(negedge clk); sel = s; en = e; wr = w; addr = a; wd = d; st = sv; irq = iv; #1;
  acc = s && e; ok = (a[1:0] == 0) && (a[7:4] == 0);
  want = 0;
  if (acc && !w) case (a) 8'h00: want = c_m; 8'h04: want = sv; 8'h08: want = i_m; 8'h0c: want = s_m; default: want = 0; endcase
  if (live) begin
    if (rdy !== 1'b1) $fatal(1, "pready");
    if (err !== (acc && !ok)) $fatal(1, "pslverr");
    if (rd !== want) $fatal(1, "prdata");
    if (ctrl !== c_m || pending !== i_m) $fatal(1, "register outputs");
  end
  @(posedge clk);
  if (acc && w && a == 8'h00) c_m = d[7:0];
  if (acc && w && a == 8'h0c) s_m = d;
  if (acc && w && a == 8'h08) i_m = i_m & ~d[7:0];
  i_m = i_m | iv;
end
endtask
task idle(input [15:0] sv, input [7:0] iv); step(0,0,0,0,0,sv,iv); endtask
task xfer(input w, input [7:0] a, input [31:0] d, input [15:0] sv, input [7:0] iv);
begin step(1,0,w,a,d,sv,0); step(1,1,w,a,d,sv,iv); end
endtask
task reset_all; begin rstn = 0; repeat(2) @(posedge clk); c_m = 0; i_m = 0; s_m = 0; live = 1; @(negedge clk); rstn = 1; end endtask
"""
task("apb_regs", "APB3 control/status register block", "interface", "medium",
     """module apb_regs (
  input pclk, input presetn,
  input psel, input penable, input pwrite, input [7:0] paddr, input [31:0] pwdata,
  output [31:0] prdata, output pready, output pslverr,
  input [15:0] status_in, input [7:0] irq_set,
  output [7:0] ctrl, output [7:0] irq_pending
);""", """  reg [7:0] ctrl_q, irq_q;
  reg [31:0] scratch_q, rd;
  wire access = psel && penable;
  wire valid = (paddr[1:0] == 0) && (paddr[7:4] == 0);
  wire irq_wr = access && pwrite && paddr == 8'h08;
  assign pready = 1'b1;
  assign pslverr = access && !valid;
  assign ctrl = ctrl_q;
  assign irq_pending = irq_q;
  always @* case (paddr)
    8'h00: rd = {24'b0, ctrl_q};
    8'h04: rd = {16'b0, status_in};
    8'h08: rd = {24'b0, irq_q};
    8'h0c: rd = scratch_q;
    default: rd = 32'b0;
  endcase
  assign prdata = (access && !pwrite) ? rd : 32'b0;
  always @(posedge pclk)
    if (!presetn) begin ctrl_q <= 0; irq_q <= 0; scratch_q <= 0; end
    else begin
      if (access && pwrite && paddr == 8'h00) ctrl_q <= pwdata[7:0];
      if (access && pwrite && paddr == 8'h0c) scratch_q <= pwdata;
      irq_q <= (irq_q & ~(irq_wr ? pwdata[7:0] : 8'b0)) | irq_set;
    end
""", """Implement `apb_regs`, an APB3 slave register block. `presetn` is synchronous and active-low; it clears every register to zero. All register updates occur on the rising edge of `pclk`.

An access phase is a cycle with `psel && penable`. A cycle with `psel && !penable` is the setup phase and must have no effect. `pready` is always 1.

| paddr | name | behaviour |
|---|---|---|
| 0x00 | CTRL | read/write, bits 7:0; bits 31:8 read as 0; drives `ctrl` |
| 0x04 | STATUS | read-only, `{16'b0, status_in}`; writes are ignored without error |
| 0x08 | IRQ | bits 7:0; write-1-to-clear; drives `irq_pending` |
| 0x0C | SCRATCH | read/write, 32 bits |

Each bit of `irq_set` sets the matching IRQ bit on the rising edge whenever it is high, with or without an APB access. If the same bit is set by `irq_set` and cleared by a write in the same cycle, it ends up set.

`pslverr` is high in an access phase when `paddr[1:0] != 0` or `paddr[7:4] != 0`, and low otherwise, combinationally. Such accesses change nothing. `prdata` shows the addressed register in a read access phase, combinationally, and is 0 in every other cycle, including error reads and write accesses.""",
     {"directed": bench(APB_DECL, """reset_all; xfer(1,8'h00,32'hffffa55a,16'h1234,0); xfer(0,8'h00,0,16'h1234,0); xfer(0,8'h04,0,16'hbeef,0); xfer(1,8'h04,32'h55,16'hbeef,0); xfer(1,8'h0c,32'hdeadbeef,0,0); xfer(0,8'h0c,0,0,0);
idle(0,8'h0f); xfer(0,8'h08,0,0,0); xfer(1,8'h08,32'h03,0,0); xfer(0,8'h08,0,0,0); xfer(1,8'h08,32'h0c,0,8'h04); xfer(0,8'h08,0,0,0);
xfer(1,8'h01,32'h1,0,0); xfer(0,8'h02,0,0,0); xfer(1,8'h10,32'hff,0,0); xfer(0,8'hf0,0,0,0); step(1,0,1,8'h00,32'h77,0,0); idle(0,0); xfer(0,8'h00,0,0,0); reset_all; xfer(0,8'h0c,0,0,0); xfer(0,8'h00,0,0,0);"""),
      "seeded": bench(APB_DECL, """reset_all; for (i=0;i<900;i=i+1) begin k = $random(seed); j = (($random(seed)&3)==0) ? $random(seed)&255 : ($random(seed)&3)*4; if (k&1) xfer(k[1], j, $random(seed), $random(seed), ($random(seed)&3)==0 ? $random(seed)&255 : 0); else if ((k&12)==0) step(1,0,k[1],j,$random(seed),$random(seed),0); else idle($random(seed), ($random(seed)&7)==0 ? 8'h81 : 0); end""")},
     [("setup_write", [("wire access = psel && penable;", "wire access = psel;")], ["directed"]),
      ("clear_wins", [("irq_q <= (irq_q & ~(irq_wr ? pwdata[7:0] : 8'b0)) | irq_set;", "irq_q <= (irq_q | irq_set) & ~(irq_wr ? pwdata[7:0] : 8'b0);")], ["directed"]),
      ("unaligned_ok", [("wire valid = (paddr[1:0] == 0) && (paddr[7:4] == 0);", "wire valid = (paddr[7:4] == 0);")], ["directed"])], repair=True)

# ---------------------------------------------------------------- AXI4-Lite
AXI_DECL = """reg clk = 0, rstn = 0; reg [3:0] awaddr = 0, araddr = 0, wstrb = 0; reg awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0; reg [31:0] wdata = 0;
wire awready, wready, bvalid, arready, rvalid; wire [1:0] bresp, rresp; wire [31:0] rdata;
axil_regs dut(clk, rstn, awaddr, awvalid, awready, wdata, wstrb, wvalid, wready, bresp, bvalid, bready, araddr, arvalid, arready, rdata, rresp, rvalid, rready);
always #5 clk = ~clk;
reg [31:0] m [0:3];
task send_aw(input [3:0] a, input integer d); integer c; begin repeat(d) @(negedge clk); awaddr = a; awvalid = 1; c = 0; @(posedge clk); while (awready !== 1'b1) begin c = c + 1; if (c > 80) $fatal(1, "awready"); @(posedge clk); end @(negedge clk); awvalid = 0; end endtask
task send_w(input [31:0] x, input [3:0] s, input integer d); integer c; begin repeat(d) @(negedge clk); wdata = x; wstrb = s; wvalid = 1; c = 0; @(posedge clk); while (wready !== 1'b1) begin c = c + 1; if (c > 80) $fatal(1, "wready"); @(posedge clk); end @(negedge clk); wvalid = 0; end endtask
task take_b(input integer stall); integer c; begin c = 0; while (bvalid !== 1'b1) begin @(negedge clk); c = c + 1; if (c > 80) $fatal(1, "bvalid"); end
 repeat(stall) begin @(negedge clk); #1; if (bvalid !== 1'b1 || bresp !== 2'b00) $fatal(1, "b stall"); if (awready !== 1'b0 || wready !== 1'b0) $fatal(1, "write ready during response"); end if (bresp !== 2'b00) $fatal(1, "bresp"); bready = 1; @(posedge clk); @(negedge clk); bready = 0; #1; if (bvalid !== 1'b0) $fatal(1, "bvalid not cleared"); end endtask
task write(input [3:0] a, input [31:0] x, input [3:0] s, input integer da, input integer dw, input integer stall); integer b; begin fork send_aw(a, da); send_w(x, s, dw); join take_b(stall);
 for (b = 0; b < 4; b = b + 1) if (s[b]) m[a[3:2]][8*b +: 8] = x[8*b +: 8]; end endtask
task read(input [3:0] a, input integer d, input integer stall); integer c; reg [31:0] e; begin repeat(d) @(negedge clk); e = m[a[3:2]]; araddr = a; arvalid = 1; c = 0; @(posedge clk); while (arready !== 1'b1) begin c = c + 1; if (c > 80) $fatal(1, "arready"); @(posedge clk); end @(negedge clk); arvalid = 0; c = 0;
 while (rvalid !== 1'b1) begin @(negedge clk); c = c + 1; if (c > 80) $fatal(1, "rvalid"); end
 repeat(stall) begin @(negedge clk); #1; if (rvalid !== 1'b1 || rdata !== e || rresp !== 2'b00) $fatal(1, "r stall"); if (arready !== 1'b0) $fatal(1, "read ready during response"); end if (rdata !== e || rresp !== 2'b00) $fatal(1, "rdata"); rready = 1; @(posedge clk); @(negedge clk); rready = 0; #1; if (rvalid !== 1'b0) $fatal(1, "rvalid not cleared"); end endtask
task reset_all; begin rstn = 0; repeat(3) @(posedge clk); @(negedge clk); rstn = 1; m[0] = 0; m[1] = 0; m[2] = 0; m[3] = 0; end endtask
"""
task("axil_regs", "AXI4-Lite four-register slave", "interface", "hard",
     """module axil_regs (
  input aclk, input aresetn,
  input [3:0] awaddr, input awvalid, output awready,
  input [31:0] wdata, input [3:0] wstrb, input wvalid, output wready,
  output [1:0] bresp, output bvalid, input bready,
  input [3:0] araddr, input arvalid, output arready,
  output [31:0] rdata, output [1:0] rresp, output rvalid, input rready
);""", """  reg aw_v, w_v, b_v, r_v;
  reg [1:0] aw_i;
  reg [31:0] w_d, r_d;
  reg [3:0] w_s;
  reg [31:0] regs [0:3];
  integer i;
  assign awready = !aw_v && !b_v;
  assign wready = !w_v && !b_v;
  assign bvalid = b_v;
  assign bresp = 2'b00;
  assign arready = !r_v;
  assign rvalid = r_v;
  assign rdata = r_d;
  assign rresp = 2'b00;
  always @(posedge aclk)
    if (!aresetn) begin
      aw_v <= 0; w_v <= 0; b_v <= 0; r_v <= 0;
      for (i = 0; i < 4; i = i + 1) regs[i] <= 32'b0;
    end else begin
      if (awvalid && awready) begin aw_v <= 1; aw_i <= awaddr[3:2]; end
      if (wvalid && wready) begin w_v <= 1; w_d <= wdata; w_s <= wstrb; end
      if (aw_v && w_v) begin
        for (i = 0; i < 4; i = i + 1) if (w_s[i]) regs[aw_i][8*i +: 8] <= w_d[8*i +: 8];
        aw_v <= 0; w_v <= 0; b_v <= 1;
      end
      if (b_v && bready) b_v <= 0;
      if (arvalid && arready) begin r_v <= 1; r_d <= regs[araddr[3:2]]; end
      if (r_v && rready) r_v <= 0;
    end
""", """Implement `axil_regs`, an AXI4-Lite slave with four 32-bit read/write registers. `aresetn` is synchronous, active-low and clears the registers and all channel state.

- Register index is `addr[3:2]`; `addr[1:0]` is ignored. All responses are OKAY (`2'b00`).
- The write address and write data channels are independent: either may complete its handshake first, or both together, with any delay between them, and the write must still complete.
- At most one write and one read are outstanding. While `bvalid` is high, `awready` and `wready` are low. While `rvalid` is high, `arready` is low. Handshake waits must be bounded: after the master presents a channel while no earlier transaction of that kind is outstanding, the slave completes the handshake within a few cycles.
- A write updates only the bytes selected by `wstrb` of the addressed register. After both channels complete, `bvalid` rises within a few cycles and holds with stable `bresp` until `bready` is high on a rising edge, then falls on the next cycle.
- After a read address handshake, `rvalid` rises within a few cycles and holds with stable `rdata`/`rresp` until `rready` is high on a rising edge, then falls on the next cycle.
- A read returns the register's contents as of its address handshake. Reads to a different register concurrent with a write are independent of that write.""",
     {"directed": bench(AXI_DECL, """reset_all; read(4'h0,0,0); write(4'h0,32'h11223344,4'hf,0,0,0); read(4'h0,0,2); write(4'h4,32'hAABBCCDD,4'h5,0,3,1); read(4'h4,0,0); write(4'h8,32'h5a5a5a5a,4'hc,4,0,3); read(4'h8,2,1); write(4'hd,32'h01020304,4'h3,1,1,0); read(4'hc,0,0); read(4'hf,0,4); reset_all; read(4'h0,0,0); read(4'hc,0,0);"""),
      "seeded": bench(AXI_DECL, """reset_all; for (i=0;i<260;i=i+1) begin j = $random(seed) & 15; k = (j + 4 + (($random(seed)&1)*4)) & 15; case ($random(seed) & 3)
0: write(j, $random(seed), $random(seed), $random(seed)&3, $random(seed)&3, $random(seed)&3);
1: read(j, $random(seed)&3, $random(seed)&3);
2: fork write(j, $random(seed), $random(seed), $random(seed)&1, $random(seed)&1, $random(seed)&1); read(k, 0, $random(seed)&1); join
default: begin write(j, $random(seed), 4'hf, 0, 0, 0); read(j, 0, 0); end endcase end""")},
     [("ignore_strobe", [("if (w_s[i]) regs[aw_i][8*i +: 8]", "regs[aw_i][8*i +: 8]")], ["directed"]),
      ("r_valid_drop", [("if (r_v && rready) r_v <= 0;", "if (r_v) r_v <= 0;")], ["directed"]),
      ("read_index", [("r_d <= regs[araddr[3:2]];", "r_d <= regs[araddr[2:1]];")], ["directed"])], repair=True)

# ---------------------------------------------------------------- AXI-Stream downsizer
AXIS_DECL = """reg clk = 0, rst = 1, s_valid = 0, s_last = 0, m_ready = 0; reg [31:0] s_data = 0; reg [3:0] s_keep = 0; wire s_ready, m_valid, m_last; wire [7:0] m_data;
axis_downsizer dut(clk, rst, s_valid, s_ready, s_data, s_keep, s_last, m_valid, m_ready, m_data, m_last);
always #5 clk = ~clk;
reg [31:0] hold = 0; integer left = 0; reg lastm = 0, live = 0, want_rdy, tookm, tooks; integer bytes;
task step(input r, input v, input [31:0] d, input [3:0] kp, input l, input rdy);
begin
  @(negedge clk); rst = r; s_valid = v; s_data = d; s_keep = kp; s_last = l; m_ready = rdy; #1;
  if (live) begin
    want_rdy = left == 0 || (left == 1 && rdy);
    if (s_ready !== want_rdy) $fatal(1, "s_ready");
    if (m_valid !== (left != 0)) $fatal(1, "m_valid");
    if (left != 0 && (m_data !== hold[7:0] || m_last !== (lastm && left == 1))) $fatal(1, "m_data/m_last");
  end
  tookm = left != 0 && rdy; tooks = v && want_rdy;
  @(posedge clk);
  if (r) begin left = 0; live = 1; end
  else begin
    if (tookm) begin hold = hold >> 8; left = left - 1; end
    if (tooks) begin hold = d; lastm = l; left = kp[3] ? 4 : kp[2] ? 3 : kp[1] ? 2 : 1; end
  end
end
endtask
function [3:0] keep_of(input integer x); keep_of = (x & 3) == 0 ? 4'h1 : (x & 3) == 1 ? 4'h3 : (x & 3) == 2 ? 4'h7 : 4'hf; endfunction
"""
task("axis_downsizer", "32-to-8 bit AXI-Stream width converter", "interface", "hard",
     """module axis_downsizer (
  input clk, input rst,
  input s_valid, output s_ready, input [31:0] s_data, input [3:0] s_keep, input s_last,
  output m_valid, input m_ready, output [7:0] m_data, output m_last
);""", """  reg [31:0] d;
  reg [2:0] left;
  reg last;
  wire have = left != 0;
  wire beat = have && m_ready;
  assign m_valid = have;
  assign m_data = d[7:0];
  assign m_last = last && left == 1;
  assign s_ready = !have || (left == 1 && m_ready);
  always @(posedge clk)
    if (rst) left <= 0;
    else if (s_valid && s_ready) begin
      d <= s_data;
      left <= s_keep[3] ? 3'd4 : s_keep[2] ? 3'd3 : s_keep[1] ? 3'd2 : 3'd1;
      last <= s_last;
    end
    else if (beat) begin d <= d >> 8; left <= left - 1; end
""", """Implement `axis_downsizer`, which converts a 32-bit stream to an 8-bit stream. `rst` is synchronous, active-high and discards any held beat.

- `s_keep` is always one of 4'b0001, 4'b0011, 4'b0111, 4'b1111 when `s_valid` is high; other values need not be handled. Only kept bytes are emitted, least-significant byte first.
- The block holds one input beat at a time. Let `left` be the bytes of the held beat not yet transferred on the master side.
- `m_valid` is high exactly when `left != 0`. `m_data` is the next byte. `m_last` is high exactly on the final byte of a held beat whose `s_last` was high.
- `s_ready` is high exactly when `left == 0`, or when `left == 1 && m_ready` (the final byte transfers in this cycle), so that consecutive beats have no bubble. `s_ready` may depend combinationally on `m_ready`.
- A master-side transfer occurs on a rising edge when `m_valid && m_ready`. A slave-side transfer occurs when `s_valid && s_ready`; the first byte of that beat is visible in the next cycle.
- While `m_valid` is high and `m_ready` is low, `m_data` and `m_last` hold. They are undefined when `m_valid` is low.""",
     {"directed": bench(AXIS_DECL, """step(1,0,0,0,0,0); step(0,1,32'h44332211,4'hf,1,1); step(0,1,32'h88776655,4'h3,0,1); step(0,0,0,0,0,1); step(0,0,0,0,0,0); step(0,0,0,0,0,1); step(0,0,0,0,0,1); step(0,0,0,0,0,1); step(0,1,32'haabbccdd,4'h7,1,0); step(0,0,0,0,0,0); step(0,0,0,0,0,1); step(0,0,0,0,0,1); step(0,0,0,0,0,1); step(0,1,32'h01,4'h1,1,1); step(0,0,0,0,0,1); step(0,1,32'h11,4'hf,0,0); step(1,0,0,0,0,0); step(0,0,0,0,0,1);"""),
      "seeded": bench(AXIS_DECL, """step(1,0,0,0,0,0); for (i=0;i<2000;i=i+1) begin j = $random(seed); step(($random(seed)&511)==0, j[0], $random(seed), keep_of($random(seed)), j[1], j[2] | j[3]); end""")},
     [("ignore_keep", [("left <= s_keep[3] ? 3'd4 : s_keep[2] ? 3'd3 : s_keep[1] ? 3'd2 : 3'd1;", "left <= 3'd4;")], ["directed"]),
      ("last_every_byte", [("assign m_last = last && left == 1;", "assign m_last = last;")], ["directed"]),
      ("shift_on_stall", [("else if (beat) begin", "else if (have) begin")], ["directed"])], repair=True)

# ---------------------------------------------------------------- arbiter with lock
RR_DECL = """parameter N = %d;
reg clk = 0, rst = 1, lock = 0, accept = 0; reg [N-1:0] req = 0; wire [N-1:0] grant;
rr_arbiter #(.N(N)) dut(clk, rst, req, lock, accept, grant);
always #5 clk = ~clk;
integer ptr = 0, owner = 0, idx; reg held = 0, found, live = 0;
reg [N-1:0] want;
task step(input r, input [N-1:0] q, input l, input a);
integer n;
begin
  @(negedge clk); rst = r; req = q; lock = l; accept = a; #1;
  found = 0; idx = 0;
  if (held && q[owner]) begin found = 1; idx = owner; end
  else for (n = 0; n < N && !found; n = n + 1) if (q[(ptr + n) %% N]) begin found = 1; idx = (ptr + n) %% N; end
  want = found ? ({{(N-1){1'b0}}, 1'b1} << idx) : {N{1'b0}};
  if (live && grant !== want) $fatal(1, "grant");
  @(posedge clk);
  if (r) begin ptr = 0; held = 0; live = 1; end
  else if (a && found) begin if (l) begin held = 1; owner = idx; end else begin held = 0; ptr = (idx + 1) %% N; end end
  else if (held && !q[owner]) held = 0;
end
endtask
"""
task("rr_arbiter", "round-robin arbiter with lock and accept", "control", "medium",
     """module rr_arbiter #(parameter N = 4) (
  input clk, input rst,
  input [N-1:0] req, input lock, input accept,
  output [N-1:0] grant
);""", """  reg [$clog2(N)-1:0] ptr, owner, idx;
  reg held, found;
  integer i, j;
  always @* begin
    found = 0; idx = 0;
    if (held && req[owner]) begin found = 1; idx = owner; end
    else for (i = 0; i < N; i = i + 1) begin
      j = (ptr + i) % N;
      if (!found && req[j]) begin found = 1; idx = j; end
    end
  end
  assign grant = found ? ({{(N-1){1'b0}}, 1'b1} << idx) : {N{1'b0}};
  always @(posedge clk)
    if (rst) begin ptr <= 0; held <= 0; end
    else if (accept && found) begin
      if (lock) begin held <= 1; owner <= idx; end
      else begin held <= 0; ptr <= (idx + 1) % N; end
    end
    else if (held && !req[owner]) held <= 0;
""", """Implement `rr_arbiter`, a combinational-grant round-robin arbiter with a lock. N >= 2. `rst` is synchronous and active-high; it sets the priority pointer to requester 0 and clears any lock.

- `grant` is one-hot or zero. It depends combinationally on `req` and on registered state.
- If a lock is held and the locked owner still requests, `grant` selects the owner regardless of the pointer.
- Otherwise, `grant` selects the first requester at or after the pointer, in increasing index with wrap-around. With no requests, `grant` is zero.
- State changes only on rising edges. When `accept` is high and `grant` is nonzero: if `lock` is high, the granted requester becomes (or stays) the locked owner and the pointer is unchanged; if `lock` is low, any lock is released and the pointer moves to the requester after the granted one, modulo N.
- When `accept` is low or `grant` is zero, the pointer does not move. A lock whose owner no longer requests is released at that edge unless a new accepted grant applies.""",
     {"directed": bench(RR_DECL % 4, """step(1,0,0,0); step(0,4'b1010,0,1); step(0,4'b1010,0,1); step(0,4'b1010,0,0); step(0,4'b1010,0,1); step(0,4'b0110,1,1); step(0,4'b0111,1,1); step(0,4'b0111,0,0); step(0,4'b0111,0,1); step(0,4'b0101,1,0); step(0,0,0,1); step(0,4'b1111,1,1); step(0,4'b1101,0,0); step(0,4'b1101,1,1); step(1,4'b1101,1,1); step(0,4'b1000,0,0);"""),
      "seeded": bench(RR_DECL % 5, """step(1,0,0,0); for (i=0;i<2000;i=i+1) begin j = $random(seed); step((j & 1023)==0, $random(seed) & $random(seed), j[10], j[11]|j[12]); end""")},
     [("advance_without_accept", [("else if (accept && found) begin", "else if (found) begin")], ["directed"]),
      ("lock_ignored", [("if (lock) begin held <= 1; owner <= idx; end", "if (1'b0) begin held <= 1; owner <= idx; end")], ["directed"]),
      ("pointer_stays", [("ptr <= (idx + 1) % N;", "ptr <= idx;")], ["directed"])], repair=True)

# ---------------------------------------------------------------- CRC32
CRC_DECL = """reg clk = 0, rst = 1, init = 0, en = 0; reg [7:0] data = 0; wire [31:0] crc;
crc32_byte dut(clk, rst, init, en, data, crc);
always #5 clk = ~clk;
reg [31:0] m = 32'hffffffff; integer b; reg live = 0;
task step(input r, input ini, input e, input [7:0] d);
begin
  @(negedge clk); rst = r; init = ini; en = e; data = d; #1;
  if (live && crc !== ~m) $fatal(1, "crc");
  @(posedge clk);
  if (r || ini) begin m = 32'hffffffff; live = 1; end
  else if (e) for (b = 0; b < 8; b = b + 1) m = (m[0] ^ d[b]) ? (m >> 1) ^ 32'hedb88320 : m >> 1;
end
endtask
"""
task("crc32_byte", "byte-wide CRC-32 engine", "datapath", "medium",
     """module crc32_byte (
  input clk, input rst,
  input init, input en, input [7:0] data,
  output [31:0] crc
);""", """  reg [31:0] s;
  function [31:0] next(input [31:0] c, input [7:0] d);
    integer i;
    begin
      next = c ^ {24'b0, d};
      for (i = 0; i < 8; i = i + 1) next = next[0] ? (next >> 1) ^ 32'hEDB88320 : next >> 1;
    end
  endfunction
  assign crc = ~s;
  always @(posedge clk)
    if (rst || init) s <= 32'hFFFFFFFF;
    else if (en) s <= next(s, data);
""", """Implement `crc32_byte`, computing CRC-32 (IEEE 802.3: reflected, polynomial 0x04C11DB7 / reflected form 0xEDB88320, initial value 0xFFFFFFFF, final XOR 0xFFFFFFFF) one byte per enabled clock.

- `rst` (synchronous, active-high) and `init` both load the initial value on a rising edge. `rst` and `init` have priority over `en`.
- When `en` is high and neither `rst` nor `init` is high, the byte `data` is absorbed on the rising edge, least-significant bit first. When `en` is low, the state holds.
- `crc` is the bitwise inverse of the internal state, with no extra latency. For example, after init and the ASCII bytes "123456789", `crc` is 0xCBF43926; directly after init, `crc` is 0.""",
     {"directed": bench(CRC_DECL, """step(1,0,0,0); step(0,0,0,0); for (i=0;i<9;i=i+1) step(0,0,1,8'h31+i); step(0,0,0,0); #1; if (crc !== 32'hcbf43926) $fatal(1, "check value"); step(0,1,1,8'h55); step(0,0,0,8'h55); step(0,0,1,8'h00); step(0,0,0,0); step(1,0,1,8'haa); step(0,0,0,0);"""),
      "seeded": bench(CRC_DECL, """step(1,0,0,0); for (i=0;i<3000;i=i+1) begin j = $random(seed); step((j&2047)==0, ((j>>11)&127)==0, j[20]|j[21], $random(seed)); end""")},
     [("wrong_poly", [("32'hEDB88320", "32'hEDB88321")], ["directed"]),
      ("no_final_xor", [("assign crc = ~s;", "assign crc = s;")], ["directed"]),
      ("en_beats_init", [("if (rst || init) s <= 32'hFFFFFFFF;\n    else if (en) s <= next(s, data);", "if (rst) s <= 32'hFFFFFFFF;\n    else if (en) s <= next(s, data);\n    else if (init) s <= 32'hFFFFFFFF;")], ["directed"])], repair=True)

# ---------------------------------------------------------------- SECDED
SEC_DECL = """reg [7:0] d = 0; wire [12:0] cw; reg [12:0] rx = 0; wire [7:0] q; wire sec, ded;
secded_codec dut(d, cw, rx, q, sec, ded);
function [12:0] enc(input [7:0] v); reg [3:0] c; reg o; begin
 c[0] = v[0]^v[1]^v[3]^v[4]^v[6]; c[1] = v[0]^v[2]^v[3]^v[5]^v[6]; c[2] = v[1]^v[2]^v[3]^v[7]; c[3] = v[4]^v[5]^v[6]^v[7]; o = ^{v,c}; enc = {o,c,v}; end endfunction
reg [3:0] sy; reg pe; reg [7:0] fx; reg es, ed;
task judge(input [12:0] r); begin
 sy[0] = r[8]^r[0]^r[1]^r[3]^r[4]^r[6]; sy[1] = r[9]^r[0]^r[2]^r[3]^r[5]^r[6]; sy[2] = r[10]^r[1]^r[2]^r[3]^r[7]; sy[3] = r[11]^r[4]^r[5]^r[6]^r[7]; pe = ^r; fx = r[7:0]; es = 0; ed = 0;
 if (pe && sy <= 12) begin es = 1; case (sy) 3: fx[0] = ~fx[0]; 5: fx[1] = ~fx[1]; 6: fx[2] = ~fx[2]; 7: fx[3] = ~fx[3]; 9: fx[4] = ~fx[4]; 10: fx[5] = ~fx[5]; 11: fx[6] = ~fx[6]; 12: fx[7] = ~fx[7]; default: ; endcase end
 else if (pe || sy != 0) ed = 1;
 rx = r; #1; if (q !== fx || sec !== es || ded !== ed) $fatal(1, "decode"); end endtask
"""
task("secded_codec", "Hamming SEC-DED encoder and decoder", "datapath", "medium",
     """module secded_codec (
  input [7:0] enc_data, output [12:0] enc_cw,
  input [12:0] dec_cw, output [7:0] dec_data, output sec, output ded
);""", """  wire [3:0] c = {enc_data[4]^enc_data[5]^enc_data[6]^enc_data[7],
                  enc_data[1]^enc_data[2]^enc_data[3]^enc_data[7],
                  enc_data[0]^enc_data[2]^enc_data[3]^enc_data[5]^enc_data[6],
                  enc_data[0]^enc_data[1]^enc_data[3]^enc_data[4]^enc_data[6]};
  assign enc_cw = {^{enc_data, c}, c, enc_data};
  wire [3:0] s = {dec_cw[11]^dec_cw[4]^dec_cw[5]^dec_cw[6]^dec_cw[7],
                  dec_cw[10]^dec_cw[1]^dec_cw[2]^dec_cw[3]^dec_cw[7],
                  dec_cw[9]^dec_cw[0]^dec_cw[2]^dec_cw[3]^dec_cw[5]^dec_cw[6],
                  dec_cw[8]^dec_cw[0]^dec_cw[1]^dec_cw[3]^dec_cw[4]^dec_cw[6]};
  wire pe = ^dec_cw;
  assign sec = pe && s <= 12;
  assign ded = (!pe && s != 0) || (pe && s > 12);
  wire [7:0] flip = !sec ? 8'b0 :
                    s == 3 ? 8'h01 : s == 5 ? 8'h02 : s == 6 ? 8'h04 : s == 7 ? 8'h08 :
                    s == 9 ? 8'h10 : s == 10 ? 8'h20 : s == 11 ? 8'h40 : s == 12 ? 8'h80 : 8'b0;
  assign dec_data = dec_cw[7:0] ^ flip;
""", """Implement `secded_codec`, a purely combinational Hamming SEC-DED codec for 8 data bits and 5 check bits.

Encoding: `enc_cw = {p, c[3:0], enc_data[7:0]}` where, writing d for `enc_data`,
c0 = d0^d1^d3^d4^d6, c1 = d0^d2^d3^d5^d6, c2 = d1^d2^d3^d7, c3 = d4^d5^d6^d7, and p is the XOR of all d and c bits.

Decoding of `dec_cw = {p, c[3:0], d[7:0]}`: compute syndrome s[3:0] where s0 = c0^d0^d1^d3^d4^d6, s1 = c1^d0^d2^d3^d5^d6, s2 = c2^d1^d2^d3^d7, s3 = c3^d4^d5^d6^d7, and pe = XOR of all 13 bits.

- pe=0, s=0: no error. `sec`=0, `ded`=0, `dec_data`=d.
- pe=1, s<=12: single-bit error. `sec`=1, `ded`=0. `dec_data` is d with the bit named by s corrected: s=3,5,6,7,9,10,11,12 correct d0,d1,d2,d3,d4,d5,d6,d7 respectively; any other s (0,1,2,4,8) means a check bit was hit and d is unchanged.
- Otherwise (pe=0 with s!=0, or pe=1 with s>12): uncorrectable. `sec`=0, `ded`=1, `dec_data`=d unchanged.""",
     {"exhaustive": bench(SEC_DECL, """for (i=0;i<256;i=i+1) begin d = i; #1; if (cw !== enc(d)) $fatal(1, "encode"); judge(enc(d)); for (j=0;j<13;j=j+1) begin judge(enc(d) ^ (13'd1 << j)); for (k=j+1;k<13;k=k+1) judge(enc(d) ^ (13'd1 << j) ^ (13'd1 << k)); end end"""),
      "seeded": bench(SEC_DECL, """for (i=0;i<9000;i=i+1) begin d = $random(seed); #1; if (cw !== enc(d)) $fatal(1, "encode"); judge($random(seed)); end for (i=0;i<8192;i=i+1) judge(i);""")},
     [("bad_parity", [("enc_data[1]^enc_data[2]^enc_data[3]^enc_data[7],", "enc_data[1]^enc_data[2]^enc_data[3],")], ["exhaustive"]),
      ("miss_invalid_syndrome", [("assign ded = (!pe && s != 0) || (pe && s > 12);", "assign ded = (!pe && s != 0);")], ["seeded"]),
      ("wrong_flip", [("s == 9 ? 8'h10", "s == 9 ? 8'h20")], ["exhaustive"])], repair=False)

# ---------------------------------------------------------------- timer
TMR_DECL = """reg clk = 0, rst = 1, enable = 0, oneshot = 0, irq_clear = 0; reg [7:0] prescale = 0; reg [15:0] compare = 0; wire [15:0] count; wire irq;
timer_irq dut(clk, rst, enable, oneshot, prescale, compare, irq_clear, count, irq);
always #5 clk = ~clk;
integer m_pre = 0, m_cnt = 0; reg m_irq = 0, m_done = 0, live = 0, tick, hit;
task step(input r, input e, input c);
begin
  @(negedge clk); rst = r; enable = e; irq_clear = c; #1;
  if (live && (count !== m_cnt || irq !== m_irq)) $fatal(1, "timer state");
  tick = e && !m_done && m_pre == prescale; hit = tick && m_cnt == compare;
  @(posedge clk);
  if (r) begin m_pre = 0; m_cnt = 0; m_irq = 0; m_done = 0; live = 1; end
  else begin
    if (e && !m_done) m_pre = tick ? 0 : m_pre + 1;
    if (!e) m_done = 0;
    if (tick) begin if (hit) begin m_cnt = 0; if (oneshot) m_done = 1; end else m_cnt = m_cnt + 1; end
    if (hit) m_irq = 1; else if (c) m_irq = 0;
  end
end
endtask
task cfg(input [7:0] p, input [15:0] v, input o); begin step(1,0,0); prescale = p; compare = v; oneshot = o; step(1,0,0); end endtask
"""
task("timer_irq", "prescaled compare timer with sticky interrupt", "control", "medium",
     """module timer_irq (
  input clk, input rst,
  input enable, input oneshot,
  input [7:0] prescale, input [15:0] compare,
  input irq_clear,
  output [15:0] count, output irq
);""", """  reg [7:0] pre;
  reg [15:0] cnt;
  reg irq_q, done;
  wire tick = enable && !done && pre == prescale;
  wire hit = tick && cnt == compare;
  assign count = cnt;
  assign irq = irq_q;
  always @(posedge clk)
    if (rst) begin pre <= 0; cnt <= 0; irq_q <= 0; done <= 0; end
    else begin
      if (enable && !done) pre <= tick ? 8'b0 : pre + 8'd1;
      if (!enable) done <= 0;
      if (tick) begin
        if (hit) begin cnt <= 0; if (oneshot) done <= 1; end
        else cnt <= cnt + 16'd1;
      end
      if (hit) irq_q <= 1;
      else if (irq_clear) irq_q <= 0;
    end
""", """Implement `timer_irq`. `rst` is synchronous, active-high and clears all state. `prescale`, `compare` and `oneshot` only change while `rst` is high; behaviour otherwise is undefined.

- While `enable` is high and the timer is not stopped, a prescaler counts every clock. When it equals `prescale` a tick occurs in that cycle and the prescaler returns to 0 on the rising edge; otherwise it increments. So a tick occurs every `prescale + 1` enabled cycles.
- `enable` low holds the prescaler and `count` unchanged and clears the stopped condition on that rising edge.
- On a tick, if `count == compare`, the event fires: `count` returns to 0 and `irq` is set. If `oneshot` is high the timer then stops: no prescaler or count updates occur until `enable` has been low for at least one rising edge. On a tick with `count != compare`, `count` increments.
- `irq` is sticky. `irq_clear` high on a rising edge clears it, unless an event fires on the same edge, in which case `irq` is set.
- `count` and `irq` are registered and show state after the most recent rising edge.""",
     {"directed": bench(TMR_DECL, """cfg(2,3,0); for (i=0;i<20;i=i+1) step(0,1,0); step(0,1,1); step(0,0,0); step(0,0,0); for (i=0;i<14;i=i+1) step(0,1,0); cfg(0,1,1); for (i=0;i<6;i=i+1) step(0,1,0); step(0,0,1); for (i=0;i<6;i=i+1) step(0,1,0); cfg(0,0,0); step(0,1,0); step(0,1,1); step(0,1,1); step(0,0,1); step(0,0,0);"""),
      "seeded": bench(TMR_DECL, """for (j=0;j<80;j=j+1) begin cfg($random(seed)&3, $random(seed)&7, $random(seed)&1); for (i=0;i<80;i=i+1) begin k = $random(seed); step(0, (k&7)!=0, (k&48)==0); end end""")},
     [("prescale_off_by_one", [("wire tick = enable && !done && pre == prescale;", "wire tick = enable && !done && pre == prescale + 8'd1;")], ["directed"]),
      ("clear_beats_set", [("if (hit) irq_q <= 1;\n      else if (irq_clear) irq_q <= 0;", "if (irq_clear) irq_q <= 0;\n      else if (hit) irq_q <= 1;")], ["directed"]),
      ("oneshot_ignored", [("if (oneshot) done <= 1;", "if (1'b0) done <= 1;")], ["directed"])], repair=True)

# ---------------------------------------------------------------- credit counter
CR_DECL = """parameter M = %d;
reg clk = 0, rst = 1, consume = 0, ret = 0; wire can_send, overflow; wire [$clog2(M+1)-1:0] credits;
credit_counter #(.MAX(M)) dut(clk, rst, consume, ret, can_send, credits, overflow);
always #5 clk = ~clk;
integer m = 0; reg ovf = 0, live = 0, tk;
task step(input r, input c, input v);
begin
  @(negedge clk); rst = r; consume = c; ret = v; #1;
  if (live && (credits !== m || can_send !== (m > 0) || overflow !== ovf)) $fatal(1, "credit state");
  tk = c && m > 0;
  @(posedge clk);
  if (r) begin m = M; ovf = 0; live = 1; end
  else if (tk && !v) m = m - 1;
  else if (!tk && v) begin if (m == M) ovf = 1; else m = m + 1; end
end
endtask
"""
task("credit_counter", "flow-control credit counter", "control", "easy",
     """module credit_counter #(parameter MAX = 8) (
  input clk, input rst,
  input consume, input ret,
  output can_send, output [$clog2(MAX+1)-1:0] credits, output overflow
);""", """  reg [$clog2(MAX+1)-1:0] n;
  reg ov;
  wire take = consume && n != 0;
  assign can_send = n != 0;
  assign credits = n;
  assign overflow = ov;
  always @(posedge clk)
    if (rst) begin n <= MAX; ov <= 0; end
    else if (take && !ret) n <= n - 1'b1;
    else if (!take && ret) begin
      if (n == MAX) ov <= 1;
      else n <= n + 1'b1;
    end
""", """Implement `credit_counter`. MAX >= 1. `rst` is synchronous, active-high, sets `credits` to MAX and clears `overflow`.

- `can_send` is high exactly when `credits != 0`.
- `consume` takes one credit on a rising edge only if `credits != 0`; `consume` while `credits == 0` has no effect.
- `ret` returns one credit on a rising edge.
- An effective consume together with `ret` leaves `credits` unchanged.
- `ret` without an effective consume while `credits == MAX` leaves `credits` at MAX and sets the sticky `overflow` flag, which only `rst` clears.
- At `credits == 0`, `consume` and `ret` in the same cycle yield `credits == 1`.""",
     {"directed": bench(CR_DECL % 2, """step(1,0,0); step(0,0,1); step(0,1,0); step(0,1,0); step(0,1,0); step(0,1,1); step(0,1,1); step(0,0,1); step(0,0,1); step(0,0,0); step(1,0,0); step(0,0,0);"""),
      "seeded": bench(CR_DECL % 5, """step(1,0,0); for (i=0;i<2000;i=i+1) begin j = $random(seed); step((j&1023)==0, j[10]|j[12], j[11]); end""")},
     [("consume_at_zero", [("wire take = consume && n != 0;", "wire take = consume;")], ["directed"]),
      ("no_saturate", [("if (n == MAX) ov <= 1;\n      else n <= n + 1'b1;", "n <= n + 1'b1;")], ["directed"])])

# ---------------------------------------------------------------- async FIFO
AF_DECL = """parameter AW = 3; parameter DP = 1 << AW;
reg wclk = 0, rclk = 0, wrst_n = 1, rrst_n = 1, wr_en = 0, rd_en = 0; reg [7:0] wdata = 0; wire wfull, rempty; wire [7:0] rdata; integer wp = 5, rp = 7;
async_fifo #(.WIDTH(8), .AW(AW)) dut(wclk, wrst_n, wr_en, wdata, wfull, rclk, rrst_n, rd_en, rdata, rempty);
always #(wp) wclk = ~wclk;
always #(rp) rclk = ~rclk;
reg [7:0] q [0:65535]; integer h = 0, t = 0, n = 0, wcount = 0, rcount = 0;
always @(posedge wclk) if (wrst_n && wr_en && wfull === 1'b0) begin if (n >= DP) $fatal(1, "overflow"); q[t] = wdata; t = t + 1; n = n + 1; wcount = wcount + 1; end
always @(posedge rclk) if (rrst_n && rd_en && rempty === 1'b0) begin if (n <= 0) $fatal(1, "underflow"); if (rdata !== q[h]) $fatal(1, "data order"); h = h + 1; n = n - 1; rcount = rcount + 1; end
task reset_all; begin #1; wrst_n = 0; rrst_n = 0; wr_en = 0; rd_en = 0; #1; if (rempty !== 1'b1 || wfull !== 1'b0) $fatal(1, "reset flags"); repeat(3) @(negedge wclk); wrst_n = 1; repeat(3) @(negedge rclk); rrst_n = 1; h = 0; t = 0; n = 0; end endtask
task wait_rempty(input v); integer c; begin c = 0; while (rempty !== v) begin @(negedge rclk); c = c + 1; if (c > 12) $fatal(1, "rempty latency"); end end endtask
task wait_wfull(input v); integer c; begin c = 0; while (wfull !== v) begin @(negedge wclk); c = c + 1; if (c > 12) $fatal(1, "wfull latency"); end end endtask
"""
AF_DIRECTED = """reset_all; repeat(4) @(negedge wclk); if (rempty !== 1'b1) $fatal(1, "not empty");
for (i = 0; i < DP; i = i + 1) begin @(negedge wclk); if (wfull !== 1'b0) $fatal(1, "full early"); wr_en = 1; wdata = i + 100; end @(negedge wclk); wr_en = 0; #1; if (wfull !== 1'b1) $fatal(1, "full must be immediate");
@(negedge wclk); wr_en = 1; wdata = 8'hee; repeat(3) @(negedge wclk); wr_en = 0; wait_rempty(1'b0); if (n != DP) $fatal(1, "write accepted while full");
for (i = 0; i < DP; i = i + 1) begin wait_rempty(1'b0); @(negedge rclk); rd_en = 1; @(posedge rclk); @(negedge rclk); rd_en = 0; end repeat(2) @(negedge rclk); if (rempty !== 1'b1) $fatal(1, "empty"); wait_wfull(1'b0); if (rcount != DP) $fatal(1, "read count");
reset_all; repeat(3) @(negedge wclk); wr_en = 1; wdata = 8'h5a; @(negedge wclk); wr_en = 0; wait_rempty(1'b0); @(negedge rclk); if (rdata !== 8'h5a) $fatal(1, "first word"); """
AF_SEEDED = """wp = 3 + ($random(seed) & 7); rp = 3 + ($random(seed) & 7); reset_all;
fork
 begin for (i = 0; i < 1200; i = i + 1) begin @(negedge wclk); wr_en = $random(seed) & 1; wdata = $random(seed); end @(negedge wclk); wr_en = 0; end
 begin for (j = 0; j < 1200; j = j + 1) begin @(negedge rclk); rd_en = ($random(seed) & 3) != 0; end @(negedge rclk); rd_en = 1; end
join
repeat(80) @(negedge rclk); if (n != 0 || rempty !== 1'b1) $fatal(1, "not drained"); """
task("async_fifo", "dual-clock Gray-pointer FIFO", "cdc", "hard",
     """module async_fifo #(parameter WIDTH = 8, parameter AW = 3) (
  input wclk, input wrst_n, input wr_en, input [WIDTH-1:0] wdata, output wfull,
  input rclk, input rrst_n, input rd_en, output [WIDTH-1:0] rdata, output rempty
);""", """  reg [WIDTH-1:0] mem [0:(1<<AW)-1];
  reg [AW:0] wbin, wgray, rbin, rgray, wq1, wq2, rq1, rq2;
  wire [AW:0] wbin_n = wbin + ((wr_en && !wfull) ? 1'b1 : 1'b0);
  wire [AW:0] rbin_n = rbin + ((rd_en && !rempty) ? 1'b1 : 1'b0);
  assign wfull = wgray == {~wq2[AW:AW-1], wq2[AW-2:0]};
  assign rempty = rgray == rq2;
  assign rdata = mem[rbin[AW-1:0]];
  always @(posedge wclk or negedge wrst_n)
    if (!wrst_n) begin wbin <= 0; wgray <= 0; wq1 <= 0; wq2 <= 0; end
    else begin
      if (wr_en && !wfull) mem[wbin[AW-1:0]] <= wdata;
      wbin <= wbin_n; wgray <= wbin_n ^ (wbin_n >> 1);
      wq1 <= rgray; wq2 <= wq1;
    end
  always @(posedge rclk or negedge rrst_n)
    if (!rrst_n) begin rbin <= 0; rgray <= 0; rq1 <= 0; rq2 <= 0; end
    else begin
      rbin <= rbin_n; rgray <= rbin_n ^ (rbin_n >> 1);
      rq1 <= wgray; rq2 <= rq1;
    end
""", """Implement `async_fifo`, a dual-clock FIFO of depth 2^AW (AW >= 2) with Gray-coded pointers synchronized through two flip-flops in the destination domain. `wclk` and `rclk` have arbitrary unrelated phase. `wrst_n` and `rrst_n` are asynchronous and active-low; both are asserted together to reset.

- During reset `rempty` is 1 and `wfull` is 0.
- A write is accepted on a rising `wclk` edge when `wr_en && !wfull`; a read on a rising `rclk` edge when `rd_en && !rempty`. Requests while full or empty are ignored.
- `rdata` is first-word-fall-through: while `rempty` is low it shows the oldest entry before the read is issued.
- `wfull` and `rempty` are conservative: the FIFO never overflows or underflows, and data is delivered in order without loss. `wfull` must be high in the cycle directly after the write that fills the FIFO when no read has occurred. `rempty` must be high in the cycle directly after the read that drains it when no write has occurred.
- Flag release is bounded by the synchronizers: after a write into an empty FIFO `rempty` falls within 12 `rclk` cycles, and after a read from a full FIFO `wfull` falls within 12 `wclk` cycles.""",
     {"directed": bench(AF_DECL, AF_DIRECTED), "seeded": bench(AF_DECL, AF_SEEDED)},
     [("full_equals_empty", [("assign wfull = wgray == {~wq2[AW:AW-1], wq2[AW-2:0]};", "assign wfull = wgray == wq2;")], ["directed"]),
      ("underflow", [("wire [AW:0] rbin_n = rbin + ((rd_en && !rempty) ? 1'b1 : 1'b0);", "wire [AW:0] rbin_n = rbin + (rd_en ? 1'b1 : 1'b0);")], ["seeded"])])

# ---------------------------------------------------------------- pipelined multiplier
MUL_DECL = """reg clk = 0, rst = 1, en = 0, iv = 0; reg signed [15:0] a = 0, b = 0; wire ov; wire signed [31:0] p;
mul_pipe dut(clk, rst, en, iv, a, b, ov, p);
always #5 clk = ~clk;
reg v1 = 0, v2 = 0, v3 = 0, live = 0; reg signed [31:0] d1 = 0, d2 = 0, d3 = 0;
task step(input r, input e, input i, input signed [15:0] x, input signed [15:0] y);
begin
  @(negedge clk); rst = r; en = e; iv = i; a = x; b = y; #1;
  if (live) begin if (ov !== v3) $fatal(1, "valid"); if (v3 && p !== d3) $fatal(1, "product"); end
  @(posedge clk);
  if (r) begin v1 = 0; v2 = 0; v3 = 0; live = 1; end
  else if (e) begin v3 = v2; d3 = d2; v2 = v1; d2 = d1; v1 = i; d1 = x * y; end
end
endtask
"""
task("mul_pipe", "three-stage signed multiplier with stall", "datapath", "medium",
     """module mul_pipe (
  input clk, input rst, input en, input in_valid,
  input signed [15:0] a, input signed [15:0] b,
  output out_valid, output signed [31:0] p
);""", """  reg signed [15:0] a_r, b_r;
  reg signed [31:0] p1, p2;
  reg v1, v2, v3;
  assign p = p2;
  assign out_valid = v3;
  always @(posedge clk)
    if (rst) begin v1 <= 0; v2 <= 0; v3 <= 0; end
    else if (en) begin v1 <= in_valid; v2 <= v1; v3 <= v2; end
  always @(posedge clk)
    if (en) begin a_r <= a; b_r <= b; p1 <= a_r * b_r; p2 <= p1; end
""", """Implement `mul_pipe`, a signed 16x16 multiplier with exactly three pipeline stages. `rst` is synchronous and active-high; it clears the valid bits of all stages. `p` is two's complement.

- When `en` is high on a rising edge, all three stages advance together and `in_valid`, `a` and `b` are sampled. When `en` is low, every stage holds, including valid bits.
- An input sampled on enabled edge E appears with `out_valid` high after enabled edge E+2, i.e. it is visible in the cycle after the third enabled edge that includes E, with `p == a * b` as signed values.
- `p` is only defined while `out_valid` is high.""",
     {"directed": bench(MUL_DECL, """step(1,0,0,0,0); step(0,1,1,-3,7); step(0,1,1,-32768,-32768); step(0,1,1,32767,-32768); step(0,0,1,1,1); step(0,0,0,1,1); step(0,1,0,0,0); step(0,1,0,0,0); step(0,1,0,0,0); step(0,1,1,5,5); step(1,1,1,9,9); step(0,1,0,0,0); step(0,1,0,0,0); step(0,1,0,0,0);"""),
      "seeded": bench(MUL_DECL, """step(1,0,0,0,0); for (i=0;i<2500;i=i+1) begin j = $random(seed); step((j&2047)==0, j[12]|j[13], j[14], $random(seed), $random(seed)); end""")},
     [("unsigned_product", [("reg signed [15:0] a_r, b_r;", "reg [15:0] a_r, b_r;")], ["directed"]),
      ("valid_not_stalled", [("else if (en) begin v1 <= in_valid; v2 <= v1; v3 <= v2; end", "else begin v1 <= in_valid; v2 <= v1; v3 <= v2; end")], ["directed"]),
      ("latency_two", [("assign out_valid = v3;", "assign out_valid = v2;"), ("assign p = p2;", "assign p = p1;")], ["directed"])])


def apply_bug(text, edits, name):
    for old, new in edits:
        if text.count(old) != 1:
            raise SystemExit(f"Mutant edit is not unique: {name}: {old}")
        text = text.replace(old, new)
    return text


def emit(tid, t, reference, starter, prompt, bugs, category, tier, tags):
    base = ROOT / "tasks" / tid
    file = f"rtl/{t['name']}.sv"
    for sub, text in (("reference", reference), ("starter", starter)):
        p = base / sub / file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    (base / "prompt.md").write_text(f"# {t['name']}\n\n{t['spec']}\n\nInterface:\n\n```systemverilog\n{t['header']}\n```{prompt}")
    (base / "checks").mkdir(parents=True, exist_ok=True)
    checks = []
    for cid, text in t["checks"].items():
        (base / "checks" / f"{cid}.sv").write_text(text)
        checks.append({"id": cid, "tb": f"checks/{cid}.sv", "top": "tb", "description": f"{t['title']}: {cid}"})
    mutants = []
    for name, edits, expected in bugs:
        p = base / "mutants" / name / file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(apply_bug(reference, edits, f"{tid}/{name}"))
        mutants.append({"id": name, "path": f"mutants/{name}", "expected_fail_checks": expected})
    return {"id": tid, "category": category, "title": t["title"], "path": f"tasks/{tid}", "files": [file], "checks": checks,
            "mutants": mutants, "difficulty": t["difficulty"], "domain": t["domain"], "tier": tier,
            "seed_sensitive": True, "tags": tags}


def main():
    if (ROOT / "tasks").exists():
        shutil.rmtree(ROOT / "tasks")
    tasks = []
    for t in T:
        reference = t["header"] + "\n" + t["body"] + "endmodule\n"
        stub = t["header"] + "\n  // Implement the specified behaviour here.\nendmodule\n"
        tasks.append(emit(t["name"], t, reference, stub, COMMON_NOTE, t["bugs"][:2], "generation", "soc_block", ["soc_block", "locally_authored"]))
        if t["repair"]:
            starter = apply_bug(reference, t["bugs"][0][1], t["name"])
            tasks.append(emit(t["name"] + "_repair", t, reference, starter, REPAIR_NOTE + COMMON_NOTE, t["bugs"][1:3], "repair", "soc_repair",
                              ["soc_repair", "injected_defect", "locally_authored"]))
    (ROOT / "suite.json").write_text(json.dumps({
        "schema_version": 1, "id": "soc-blocks-v1", "title": "Locally authored SoC-style blocks", "origin": "locally_authored",
        "difficulty_basis": "author_judgement", "tasks": tasks}, indent=2, ensure_ascii=False) + "\n")
    print(len(tasks), "tasks")


if __name__ == "__main__":
    main()
