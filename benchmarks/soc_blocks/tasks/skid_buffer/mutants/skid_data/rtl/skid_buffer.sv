module skid_buffer #(parameter WIDTH = 32) (
  input clk, input rst,
  input s_valid, output s_ready, input [WIDTH-1:0] s_data,
  output m_valid, input m_ready, output [WIDTH-1:0] m_data
);
  reg [WIDTH-1:0] out_d, skid_d;
  reg out_v, skid_v;
  assign s_ready = !skid_v;
  assign m_valid = out_v;
  assign m_data = out_d;
  wire out_load = !out_v || m_ready;
  always @(posedge clk)
    if (rst) begin out_v <= 0; skid_v <= 0; end
    else if (out_load) begin
      if (skid_v) begin out_d <= s_data; out_v <= 1; skid_v <= 0; end
      else begin out_v <= s_valid; if (s_valid) out_d <= s_data; end
    end
    else if (s_valid && s_ready) begin skid_d <= s_data; skid_v <= 1; end
endmodule
