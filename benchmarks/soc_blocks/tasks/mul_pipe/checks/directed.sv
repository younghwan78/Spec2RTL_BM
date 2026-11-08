`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
reg clk = 0, rst = 1, en = 0, iv = 0; reg signed [15:0] a = 0, b = 0; wire ov; wire signed [31:0] p;
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

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
step(1,0,0,0,0); step(0,1,1,-3,7); step(0,1,1,-32768,-32768); step(0,1,1,32767,-32768); step(0,0,1,1,1); step(0,0,0,1,1); step(0,1,0,0,0); step(0,1,0,0,0); step(0,1,0,0,0); step(0,1,1,5,5); step(1,1,1,9,9); step(0,1,0,0,0); step(0,1,0,0,0); step(0,1,0,0,0);
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
