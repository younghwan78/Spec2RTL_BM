`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,accept=0;reg[1:0]req=0;wire[1:0]grant;integer i;reg pref=0;reg[1:0]exp;round_robin dut(clk,rst,accept,req,grant);always #5 clk=~clk;task step;input r,a;input[1:0]q;begin @(negedge clk);rst=r;accept=a;req=q;#1;case(q)0:exp=0;1:exp=1;2:exp=2;3:exp=pref?2:1;endcase if(!r&&grant!==exp)$fatal(1,"grant mismatch");@(posedge clk);if(r)pref=0;else if(a&&exp!=0)pref=exp[0];#1;end endtask
integer seed; integer ignored; initial begin seed=1; ignored=$value$plusargs("SEED=%d",seed);
step(1,0,0);for(i=0;i<500;i=i+1)step(($random(seed)&63)==0,$random(seed)&1,$random(seed)&3);
$display("HWBENCH_PASS"); $finish; end
initial begin #100000; $fatal(1,"timeout"); end
endmodule
