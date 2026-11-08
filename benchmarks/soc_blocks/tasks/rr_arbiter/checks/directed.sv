`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
parameter N = 4;
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
  else for (n = 0; n < N && !found; n = n + 1) if (q[(ptr + n) % N]) begin found = 1; idx = (ptr + n) % N; end
  want = found ? ({{(N-1){1'b0}}, 1'b1} << idx) : {N{1'b0}};
  if (live && grant !== want) $fatal(1, "grant");
  @(posedge clk);
  if (r) begin ptr = 0; held = 0; live = 1; end
  else if (a && found) begin if (l) begin held = 1; owner = idx; end else begin held = 0; ptr = (idx + 1) % N; end end
  else if (held && !q[owner]) held = 0;
end
endtask

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
step(1,0,0,0); step(0,4'b1010,0,1); step(0,4'b1010,0,1); step(0,4'b1010,0,0); step(0,4'b1010,0,1); step(0,4'b0110,1,1); step(0,4'b0111,1,1); step(0,4'b0111,0,0); step(0,4'b0111,0,1); step(0,4'b0101,1,0); step(0,0,0,1); step(0,4'b1111,1,1); step(0,4'b1101,0,0); step(0,4'b1101,1,1); step(1,4'b1101,1,1); step(0,4'b1000,0,0);
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
