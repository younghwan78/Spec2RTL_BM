module rr_arbiter #(parameter N = 4) (
  input clk, input rst,
  input [N-1:0] req, input lock, input accept,
  output [N-1:0] grant
);
  // Thermometer mask arbitration instead of an index search.
  reg [N-1:0] mask, lk;
  wire hold = |(lk & req);
  wire [N-1:0] mreq = req & mask;
  wire [N-1:0] pick = (|mreq) ? (mreq & (~mreq + 1'b1)) : (req & (~req + 1'b1));
  assign grant = hold ? (lk & req) : pick;
  always @(posedge clk)
    if (rst) begin mask <= {N{1'b1}}; lk <= 0; end
    else if (accept && |grant) begin
      if (lock) lk <= grant;
      else begin lk <= 0; mask <= ((grant[N-1]) ? {N{1'b1}} : ~((grant << 1) - 1'b1)); end
    end
    else if (!hold) lk <= 0;
endmodule
