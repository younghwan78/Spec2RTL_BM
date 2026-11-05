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
load(8'h99);seen=0;for(i=0;i<255;i=i+1)begin if((^lfsr_out)===1'bx || lfsr_out===0)$fatal(1,"invalid state");if(seen[lfsr_out])$fatal(1,"early repetition");seen[lfsr_out]=1;@(posedge clock);#1;end if(lfsr_out!==8'h99 || seen[255:1]!=={255{1'b1}})$fatal(1,"period/state coverage");
$display("HWBENCH_PASS");$finish;end
initial begin #2000000;$fatal(1,"timeout");end
endmodule
