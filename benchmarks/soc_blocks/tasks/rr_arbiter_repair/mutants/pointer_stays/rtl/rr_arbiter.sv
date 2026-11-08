module rr_arbiter #(parameter N = 4) (
  input clk, input rst,
  input [N-1:0] req, input lock, input accept,
  output [N-1:0] grant
);
  reg [$clog2(N)-1:0] ptr, owner, idx;
  reg held, found;
  integer i, j;
  always @* begin
    found = 0; idx = 0;
    if (held && req[owner]) begin found = 1; idx = owner; end
    else for (i = 0; i < N; i = i + 1) begin
      j = (ptr + i) % N;
      if (!found && req[j]) begin found = 1; idx = j; end
    end
  end
  assign grant = found ? ({{(N-1){1'b0}}, 1'b1} << idx) : {N{1'b0}};
  always @(posedge clk)
    if (rst) begin ptr <= 0; held <= 0; end
    else if (accept && found) begin
      if (lock) begin held <= 1; owner <= idx; end
      else begin held <= 0; ptr <= idx; end
    end
    else if (held && !req[owner]) held <= 0;
endmodule
