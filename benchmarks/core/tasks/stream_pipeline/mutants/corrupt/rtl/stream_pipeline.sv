module stream_pipeline(input clk,rst,in_valid, input [7:0] in_data, output in_ready, input out_ready, output out_valid, output [7:0] out_data);
elastic_stage u(clk,rst,in_valid,8'b0,in_ready,out_ready,out_valid,out_data);
endmodule
