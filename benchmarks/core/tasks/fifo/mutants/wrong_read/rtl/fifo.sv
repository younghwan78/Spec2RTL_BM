module fifo(input clk,rst,in_valid, input [7:0] in_data, output in_ready, input out_ready, output out_valid, output [7:0] out_data);
reg [7:0] mem[0:1]; reg rd,wr; reg [1:0] n;
wire push=in_valid&&in_ready; wire pop=out_valid&&out_ready;
assign in_ready=(n<2); assign out_valid=(n!=0); assign out_data=mem[wr];
always @(posedge clk) if(rst) begin rd<=0;wr<=0;n<=0;end else begin
if(push) begin mem[wr]<=in_data;wr<=~wr;end
if(pop) rd<=~rd;
case({push,pop}) 2'b10:n<=n+1;2'b01:n<=n-1;default:n<=n;endcase end
endmodule
