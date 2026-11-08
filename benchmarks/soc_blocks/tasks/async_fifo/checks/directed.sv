`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
parameter AW = 3; parameter DP = 1 << AW;
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

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
reset_all; repeat(4) @(negedge wclk); if (rempty !== 1'b1) $fatal(1, "not empty");
for (i = 0; i < DP; i = i + 1) begin @(negedge wclk); if (wfull !== 1'b0) $fatal(1, "full early"); wr_en = 1; wdata = i + 100; end @(negedge wclk); wr_en = 0; #1; if (wfull !== 1'b1) $fatal(1, "full must be immediate");
@(negedge wclk); wr_en = 1; wdata = 8'hee; repeat(3) @(negedge wclk); wr_en = 0; wait_rempty(1'b0); if (n != DP) $fatal(1, "write accepted while full");
for (i = 0; i < DP; i = i + 1) begin wait_rempty(1'b0); @(negedge rclk); rd_en = 1; @(posedge rclk); @(negedge rclk); rd_en = 0; end repeat(2) @(negedge rclk); if (rempty !== 1'b1) $fatal(1, "empty"); wait_wfull(1'b0); if (rcount != DP) $fatal(1, "read count");
reset_all; repeat(3) @(negedge wclk); wr_en = 1; wdata = 8'h5a; @(negedge wclk); wr_en = 0; wait_rempty(1'b0); @(negedge rclk); if (rdata !== 8'h5a) $fatal(1, "first word"); 
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
