`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
reg clk = 0, rst = 1, enable = 0, oneshot = 0, irq_clear = 0; reg [7:0] prescale = 0; reg [15:0] compare = 0; wire [15:0] count; wire irq;
timer_irq dut(clk, rst, enable, oneshot, prescale, compare, irq_clear, count, irq);
always #5 clk = ~clk;
integer m_pre = 0, m_cnt = 0; reg m_irq = 0, m_done = 0, live = 0, tick, hit;
task step(input r, input e, input c);
begin
  @(negedge clk); rst = r; enable = e; irq_clear = c; #1;
  if (live && (count !== m_cnt || irq !== m_irq)) $fatal(1, "timer state");
  tick = e && !m_done && m_pre == prescale; hit = tick && m_cnt == compare;
  @(posedge clk);
  if (r) begin m_pre = 0; m_cnt = 0; m_irq = 0; m_done = 0; live = 1; end
  else begin
    if (e && !m_done) m_pre = tick ? 0 : m_pre + 1;
    if (!e) m_done = 0;
    if (tick) begin if (hit) begin m_cnt = 0; if (oneshot) m_done = 1; end else m_cnt = m_cnt + 1; end
    if (hit) m_irq = 1; else if (c) m_irq = 0;
  end
end
endtask
task cfg(input [7:0] p, input [15:0] v, input o); begin step(1,0,0); prescale = p; compare = v; oneshot = o; step(1,0,0); end endtask

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
for (j=0;j<80;j=j+1) begin cfg($random(seed)&3, $random(seed)&7, $random(seed)&1); for (i=0;i<80;i=i+1) begin k = $random(seed); step(0, (k&7)!=0, (k&48)==0); end end
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
