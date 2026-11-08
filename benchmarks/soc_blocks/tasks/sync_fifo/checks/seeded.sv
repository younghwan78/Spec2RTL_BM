`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
parameter D = 5; parameter W = 12;
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

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
step(1,0,0,0); for (i=0;i<1500;i=i+1) step(($random(seed)&127)==0, $random(seed)&1, $random(seed), $random(seed)&1); for (i=0;i<8;i=i+1) step(0,0,0,1);
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
