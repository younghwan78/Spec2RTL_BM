`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
reg clk = 0, rst = 1, s_valid = 0, s_last = 0, m_ready = 0; reg [31:0] s_data = 0; reg [3:0] s_keep = 0; wire s_ready, m_valid, m_last; wire [7:0] m_data;
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

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
step(1,0,0,0,0,0); for (i=0;i<2000;i=i+1) begin j = $random(seed); step(($random(seed)&511)==0, j[0], $random(seed), keep_of($random(seed)), j[1], j[2] | j[3]); end
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
