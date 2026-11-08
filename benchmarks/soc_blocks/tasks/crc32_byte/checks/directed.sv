`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
reg clk = 0, rst = 1, init = 0, en = 0; reg [7:0] data = 0; wire [31:0] crc;
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

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
step(1,0,0,0); step(0,0,0,0); for (i=0;i<9;i=i+1) step(0,0,1,8'h31+i); step(0,0,0,0); #1; if (crc !== 32'hcbf43926) $fatal(1, "check value"); step(0,1,1,8'h55); step(0,0,0,8'h55); step(0,0,1,8'h00); step(0,0,0,0); step(1,0,1,8'haa); step(0,0,0,0);
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
