module multi_pipe_8bit#(
    parameter size = 8
)(
          clk,      
          rst_n,       
          mul_a,       
          mul_b, 
          mul_en_in,
 
          mul_en_out,      
          mul_out    
);
input clk;
input rst_n;
input mul_en_in;
input [size-1:0] mul_a;
input [size-1:0] mul_b;
output reg mul_en_out;
output reg [size*2-1:0] mul_out;
  // Implement the specified behaviour here.
endmodule
