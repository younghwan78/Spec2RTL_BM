`timescale 1ns/1ps
module tb;
reg clock=0, reset=1; reg[7:0] lfsr_seed=8'h99; wire[7:0] lfsr_out;
lfsr_8bit dut(clock,reset,lfsr_seed,lfsr_out);
always #5 clock=~clock;
reg[7:0] expected; reg[255:0] seen; integer i,s,seed,ignored;
function[7:0] nxt(input[7:0] q); begin nxt=(q>>1) ^ (q[0]?8'hb1:8'h00); end endfunction
task load(input[7:0] v); begin @(negedge clock);reset=1;lfsr_seed=v;#1;reset=0;#1;
if(lfsr_out!==v)$fatal(1,"async reset seed mismatch got=%h expected=%h",lfsr_out,v);
@(negedge clock);reset=1;end endtask
initial begin seed=1; ignored=$value$plusargs("SEED=%d",seed);
for(s=1;s<256;s=s+1)begin load(s);expected=s;for(i=0;i<16;i=i+1)begin @(posedge clock);expected=nxt(expected);#1;if(lfsr_out!==expected)$fatal(1,"transition mismatch");end end
$display("HWBENCH_PASS");$finish;end
initial begin #2000000;$fatal(1,"timeout");end
endmodule
