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
wp = 3 + ($random(seed) & 7); rp = 3 + ($random(seed) & 7); reset_all;
fork
 begin for (i = 0; i < 1200; i = i + 1) begin @(negedge wclk); wr_en = $random(seed) & 1; wdata = $random(seed); end @(negedge wclk); wr_en = 0; end
 begin for (j = 0; j < 1200; j = j + 1) begin @(negedge rclk); rd_en = ($random(seed) & 3) != 0; end @(negedge rclk); rd_en = 1; end
join
repeat(80) @(negedge rclk); if (n != 0 || rempty !== 1'b1) $fatal(1, "not drained"); 
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
