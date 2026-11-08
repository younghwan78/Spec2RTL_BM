`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
reg clk = 0, rstn = 0, sel = 0, en = 0, wr = 0; reg [7:0] addr = 0; reg [31:0] wd = 0; wire [31:0] rd; wire rdy, err;
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

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
reset_all; xfer(1,8'h00,32'hffffa55a,16'h1234,0); xfer(0,8'h00,0,16'h1234,0); xfer(0,8'h04,0,16'hbeef,0); xfer(1,8'h04,32'h55,16'hbeef,0); xfer(1,8'h0c,32'hdeadbeef,0,0); xfer(0,8'h0c,0,0,0);
idle(0,8'h0f); xfer(0,8'h08,0,0,0); xfer(1,8'h08,32'h03,0,0); xfer(0,8'h08,0,0,0); xfer(1,8'h08,32'h0c,0,8'h04); xfer(0,8'h08,0,0,0);
xfer(1,8'h01,32'h1,0,0); xfer(0,8'h02,0,0,0); xfer(1,8'h10,32'hff,0,0); xfer(0,8'hf0,0,0,0); step(1,0,1,8'h00,32'h77,0,0); idle(0,0); xfer(0,8'h00,0,0,0); reset_all; xfer(0,8'h0c,0,0,0); xfer(0,8'h00,0,0,0);
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
