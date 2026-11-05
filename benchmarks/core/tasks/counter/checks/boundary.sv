`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,en=0;wire [7:0] count;integer i,expected;counter dut(clk,rst,en,count);always #5 clk=~clk;task step;input r,e;begin @(negedge clk);rst=r;en=e;@(posedge clk);if(r)expected=0;else if(e)expected=(expected+1)%256;#1;if(count!==expected[7:0])$fatal(1,"count mismatch");end endtask
integer seed; integer ignored; initial begin seed=1; ignored=$value$plusargs("SEED=%d",seed);
expected=0;step(1,1);step(0,1);step(0,0);
$display("HWBENCH_PASS"); $finish; end
initial begin #100000; $fatal(1,"timeout"); end
endmodule
