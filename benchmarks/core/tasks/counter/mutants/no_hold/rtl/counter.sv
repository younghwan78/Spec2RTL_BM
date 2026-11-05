module counter(input clk,rst,en, output reg [7:0] count);
always @(posedge clk) if(rst) count<=0; else count<=count+1'b1;
endmodule
