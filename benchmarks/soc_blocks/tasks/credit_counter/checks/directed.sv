`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
parameter M = 2;
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

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
step(1,0,0); step(0,0,1); step(0,1,0); step(0,1,0); step(0,1,0); step(0,1,1); step(0,1,1); step(0,0,1); step(0,0,1); step(0,0,0); step(1,0,0); step(0,0,0);
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
