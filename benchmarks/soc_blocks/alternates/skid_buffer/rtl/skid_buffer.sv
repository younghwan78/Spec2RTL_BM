module skid_buffer #(parameter WIDTH = 32) (
  input clk, input rst,
  input s_valid, output s_ready, input [WIDTH-1:0] s_data,
  output m_valid, input m_ready, output [WIDTH-1:0] m_data
);
  // Two-slot ring with read and write indices.
  reg [WIDTH-1:0] m [0:1];
  reg wi, ri; reg [1:0] n;
  assign s_ready = n != 2;
  assign m_valid = n != 0;
  assign m_data = m[ri];
  wire p = s_valid && s_ready, g = m_valid && m_ready;
  always @(posedge clk)
    if (rst) begin wi <= 0; ri <= 0; n <= 0; end
    else begin
      if (p) begin m[wi] <= s_data; wi <= ~wi; end
      if (g) ri <= ~ri;
      n <= n + p - g;
    end
endmodule
