module skid_buffer #(parameter WIDTH = 32) (
  input clk, input rst,
  input s_valid, output s_ready, input [WIDTH-1:0] s_data,
  output m_valid, input m_ready, output [WIDTH-1:0] m_data
);
  // Implement the specified behaviour here.
endmodule
