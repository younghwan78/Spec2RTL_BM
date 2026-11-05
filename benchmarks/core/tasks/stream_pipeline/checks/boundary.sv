`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,in_valid=0,out_ready=0;reg[7:0]in_data=0;wire in_ready,out_valid;wire[7:0]out_data;integer i,n=0,head=0,tail=0;reg[7:0]q[0:4095];reg push,pop;stream_pipeline dut(clk,rst,in_valid,in_data,in_ready,out_ready,out_valid,out_data);always #5 clk=~clk;task step;input r,v,ready;input[7:0]d;begin @(negedge clk);rst=r;in_valid=v;out_ready=ready;in_data=d;#1;if(!r)begin if(in_ready!==(n==0||ready)||out_valid!==(n>0))$fatal(1,"fifo flags");if(n>0&&out_data!==q[head])$fatal(1,"fifo order");end push=v&&((n==0)||ready);pop=ready&&(n>0);@(posedge clk);if(r)begin n=0;head=0;tail=0;end else begin if(pop)head=head+1;if(push)begin q[tail]=d;tail=tail+1;end n=n+push-pop;end #1;end endtask
integer seed; integer ignored; initial begin seed=1; ignored=$value$plusargs("SEED=%d",seed);
step(1,0,0,0);step(0,1,0,10);step(0,0,0,0);step(0,1,1,20);step(0,0,1,0);step(0,0,0,0);
$display("HWBENCH_PASS"); $finish; end
initial begin #100000; $fatal(1,"timeout"); end
endmodule
