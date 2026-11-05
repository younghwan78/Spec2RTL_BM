`timescale 1ns/1ps
module tb;
reg [7:0] a,b; wire [7:0] y; wire overflow; integer i,j,s; saturating_add dut(a,b,y,overflow); task check; begin #1; s=a+b; if(y!==(s>255?255:s)||overflow!==(s>255)) $fatal(1,"sum mismatch a=%d b=%d",a,b); end endtask
integer seed; integer ignored; initial begin seed=1; ignored=$value$plusargs("SEED=%d",seed);
for(i=0;i<1000;i=i+1) begin a=$random(seed);b=$random(seed);check;end
$display("HWBENCH_PASS"); $finish; end
initial begin #100000; $fatal(1,"timeout"); end
endmodule
