`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
reg clk = 0, rst = 1, s_valid = 0, m_ready = 0; reg [31:0] s_data = 0; wire s_ready, m_valid; wire [31:0] m_data;
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

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
step(1,0,0,0); for (i=0;i<1500;i=i+1) step(($random(seed)&255)==0, $random(seed)&1, $random(seed), $random(seed)&1); for (i=0;i<4;i=i+1) step(0,0,0,1);
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
