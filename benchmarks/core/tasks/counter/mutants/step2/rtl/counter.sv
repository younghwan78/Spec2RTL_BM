module counter(input clk,rst,en, output reg [7:0] count);
always @(posedge clk) if(rst) count<=0; else if(en) count<=count+2'd2;
endmodule
